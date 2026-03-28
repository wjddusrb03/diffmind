import * as vscode from 'vscode';
import { exec, ExecOptions } from 'child_process';
import * as path from 'path';

// ── Types ────────────────────────────────────────────────────────

interface DiffMindWarning {
    risk_level: string;
    similarity: number;
    current_file: string;
    past_file: string;
    past_commit: string;
    past_message: string;
    past_date: string;
    past_author: string;
    is_bugfix: boolean;
    reason: string;
}

interface DiffMindReviewResult {
    total_hunks: number;
    warning_count: number;
    warnings: DiffMindWarning[];
}

interface AIComment {
    file: string;
    line_range: string;
    risk_level: string;
    summary: string;
    explanation: string;
    suggestion: string;
    suggested_code: string;
    past_bug: string;
    confidence: number;
}

interface AIReviewResult {
    provider: string;
    model: string;
    overall_risk: string;
    total_warnings: number;
    false_positives: number;
    summary: string;
    comments: AIComment[];
}

// ── Globals ──────────────────────────────────────────────────────

let statusBarItem: vscode.StatusBarItem;
let diagnosticCollection: vscode.DiagnosticCollection;
let outputChannel: vscode.OutputChannel;
let autoReviewEnabled: boolean = false;
let saveDebounce: NodeJS.Timeout | undefined;

// ── Activation ───────────────────────────────────────────────────

export function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel('DiffMind');
    diagnosticCollection = vscode.languages.createDiagnosticCollection('diffmind');

    // Status bar
    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left, 50
    );
    statusBarItem.command = 'diffmind.review';
    setStatusBar('ready');
    const showBar = getConfig<boolean>('showStatusBar');
    if (showBar) {
        statusBarItem.show();
    }

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('diffmind.learn', cmdLearn),
        vscode.commands.registerCommand('diffmind.review', cmdReview),
        vscode.commands.registerCommand('diffmind.reviewStaged', cmdReviewStaged),
        vscode.commands.registerCommand('diffmind.aiReview', cmdAIReview),
        vscode.commands.registerCommand('diffmind.search', cmdSearch),
        vscode.commands.registerCommand('diffmind.stats', cmdStats),
        vscode.commands.registerCommand('diffmind.toggleAutoReview', cmdToggleAutoReview),
        statusBarItem,
        diagnosticCollection,
        outputChannel,
    );

    // Auto-review on save
    autoReviewEnabled = getConfig<boolean>('autoReviewOnSave') ?? false;
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument((doc) => {
            if (autoReviewEnabled) {
                debouncedReview();
            }
        })
    );

    // Config change listener
    context.subscriptions.push(
        vscode.workspace.onDidChangeConfiguration((e) => {
            if (e.affectsConfiguration('diffmind.autoReviewOnSave')) {
                autoReviewEnabled = getConfig<boolean>('autoReviewOnSave') ?? false;
            }
            if (e.affectsConfiguration('diffmind.showStatusBar')) {
                const show = getConfig<boolean>('showStatusBar');
                show ? statusBarItem.show() : statusBarItem.hide();
            }
        })
    );

    outputChannel.appendLine('DiffMind extension activated.');
}

export function deactivate() {
    if (saveDebounce) {
        clearTimeout(saveDebounce);
    }
}

// ── Commands ─────────────────────────────────────────────────────

async function cmdLearn() {
    const workspacePath = getWorkspacePath();
    if (!workspacePath) { return; }

    const since = await vscode.window.showInputBox({
        prompt: 'Learn from commits after date (optional)',
        placeHolder: '2024-01-01 (leave empty for all history)',
    });

    setStatusBar('learning');
    const sinceArg = since ? ` --since ${since}` : '';
    const bits = 3;

    try {
        const output = await runDiffMind(
            `learn "${workspacePath}"${sinceArg} --bits ${bits}`,
            workspacePath
        );
        outputChannel.appendLine(output);
        vscode.window.showInformationMessage(
            `DiffMind: Repository history learned successfully!`
        );
        setStatusBar('ready');
    } catch (err: any) {
        vscode.window.showErrorMessage(`DiffMind Learn failed: ${err.message}`);
        setStatusBar('error');
    }
}

async function cmdReview() {
    await doReview(false);
}

async function cmdReviewStaged() {
    await doReview(true);
}

async function doReview(staged: boolean) {
    const workspacePath = getWorkspacePath();
    if (!workspacePath) { return; }

    setStatusBar('reviewing');
    const threshold = getConfig<number>('threshold') ?? 0.75;
    const k = getConfig<number>('maxWarningsPerHunk') ?? 3;
    const stagedFlag = staged ? ' --staged' : '';

    try {
        const output = await runDiffMind(
            `review --json${stagedFlag} --threshold ${threshold} -k ${k} --path "${workspacePath}"`,
            workspacePath
        );

        // Try to parse JSON output
        let result: DiffMindReviewResult;
        try {
            result = JSON.parse(output.trim());
        } catch {
            // Not JSON - might be "No changes to review."
            outputChannel.appendLine(output);
            vscode.window.showInformationMessage(`DiffMind: ${output.trim()}`);
            setStatusBar('ready');
            return;
        }

        // Clear old diagnostics
        diagnosticCollection.clear();

        if (result.warning_count === 0) {
            vscode.window.showInformationMessage(
                `DiffMind: ${result.total_hunks} hunks reviewed - no bug patterns found! ✓`
            );
            setStatusBar('clean');
            return;
        }

        // Show diagnostics
        applyDiagnostics(result.warnings, workspacePath);

        // Show summary
        const highCount = result.warnings.filter(w => w.risk_level === 'HIGH').length;
        const medCount = result.warnings.filter(w => w.risk_level === 'MEDIUM').length;

        const msg = `DiffMind: ${result.warning_count} warnings found` +
            (highCount > 0 ? ` (${highCount} HIGH)` : '') +
            (medCount > 0 ? ` (${medCount} MEDIUM)` : '');

        if (highCount > 0) {
            const action = await vscode.window.showWarningMessage(
                msg, 'Show Details', 'AI Review'
            );
            if (action === 'Show Details') {
                showReviewPanel(result);
            } else if (action === 'AI Review') {
                cmdAIReview();
            }
        } else {
            vscode.window.showInformationMessage(msg);
        }

        setStatusBar('warnings', result.warning_count);

    } catch (err: any) {
        if (err.message.includes('No changes')) {
            vscode.window.showInformationMessage('DiffMind: No changes to review.');
            setStatusBar('ready');
        } else {
            vscode.window.showErrorMessage(`DiffMind Review failed: ${err.message}`);
            setStatusBar('error');
        }
    }
}

async function cmdAIReview() {
    const workspacePath = getWorkspacePath();
    if (!workspacePath) { return; }

    const provider = getConfig<string>('aiProvider') ?? 'claude';
    const lang = getConfig<string>('aiLanguage') ?? 'en';

    setStatusBar('ai-reviewing');

    try {
        const output = await runDiffMind(
            `connect ai-review --json --provider ${provider} --lang ${lang} --path "${workspacePath}"`,
            workspacePath,
            120000  // 2 min timeout for LLM
        );

        let result: AIReviewResult;
        try {
            result = JSON.parse(output.trim());
        } catch {
            outputChannel.appendLine(output);
            vscode.window.showInformationMessage(`DiffMind: ${output.trim()}`);
            setStatusBar('ready');
            return;
        }

        showAIReviewPanel(result);

        const riskEmoji = { HIGH: '🔴', MEDIUM: '🟡', LOW: '🟢', CLEAN: '✅' };
        const emoji = (riskEmoji as any)[result.overall_risk] || '';
        vscode.window.showInformationMessage(
            `DiffMind AI: ${emoji} ${result.overall_risk} - ` +
            `${result.total_warnings} warnings, ${result.false_positives} false positives`
        );

        setStatusBar('ready');

    } catch (err: any) {
        vscode.window.showErrorMessage(`DiffMind AI Review failed: ${err.message}`);
        setStatusBar('error');
    }
}

async function cmdSearch() {
    const workspacePath = getWorkspacePath();
    if (!workspacePath) { return; }

    const query = await vscode.window.showInputBox({
        prompt: 'Search bug history',
        placeHolder: 'e.g. "null check missing", "authentication error"',
    });
    if (!query) { return; }

    const langFilter = await vscode.window.showQuickPick(
        ['(all languages)', 'python', 'javascript', 'typescript', 'java', 'go', 'rust', 'c', 'cpp'],
        { placeHolder: 'Filter by language (optional)' }
    );

    let cmd = `search "${query}" --path "${workspacePath}" -k 10`;
    if (langFilter && langFilter !== '(all languages)') {
        cmd += ` --lang ${langFilter}`;
    }

    try {
        const output = await runDiffMind(cmd, workspacePath);
        outputChannel.clear();
        outputChannel.appendLine(`🔍 DiffMind Search: "${query}"\n`);
        outputChannel.appendLine(output);
        outputChannel.show();
    } catch (err: any) {
        vscode.window.showErrorMessage(`DiffMind Search failed: ${err.message}`);
    }
}

async function cmdStats() {
    const workspacePath = getWorkspacePath();
    if (!workspacePath) { return; }

    try {
        const output = await runDiffMind(
            `stats --path "${workspacePath}"`, workspacePath
        );
        outputChannel.clear();
        outputChannel.appendLine(output);
        outputChannel.show();
    } catch (err: any) {
        vscode.window.showErrorMessage(`DiffMind Stats failed: ${err.message}`);
    }
}

function cmdToggleAutoReview() {
    autoReviewEnabled = !autoReviewEnabled;
    const config = vscode.workspace.getConfiguration('diffmind');
    config.update('autoReviewOnSave', autoReviewEnabled, true);
    vscode.window.showInformationMessage(
        `DiffMind: Auto-review on save ${autoReviewEnabled ? 'enabled' : 'disabled'}`
    );
}

// ── Diagnostics ──────────────────────────────────────────────────

function applyDiagnostics(warnings: DiffMindWarning[], workspacePath: string) {
    const fileMap = new Map<string, vscode.Diagnostic[]>();

    for (const w of warnings) {
        const filePath = path.isAbsolute(w.current_file)
            ? w.current_file
            : path.join(workspacePath, w.current_file);

        const uri = vscode.Uri.file(filePath);
        const key = uri.fsPath;

        if (!fileMap.has(key)) {
            fileMap.set(key, []);
        }

        const severity = w.risk_level === 'HIGH'
            ? vscode.DiagnosticSeverity.Error
            : w.risk_level === 'MEDIUM'
                ? vscode.DiagnosticSeverity.Warning
                : vscode.DiagnosticSeverity.Information;

        const range = new vscode.Range(0, 0, 0, 100);

        const diag = new vscode.Diagnostic(
            range,
            `[DiffMind ${w.risk_level}] ${Math.round(w.similarity * 100)}% similar to ` +
            `${w.past_commit}: ${w.past_message}`,
            severity
        );
        diag.source = 'DiffMind';
        diag.code = w.is_bugfix ? 'bugfix-pattern' : 'similar-pattern';

        fileMap.get(key)!.push(diag);
    }

    for (const [filePath, diags] of fileMap) {
        diagnosticCollection.set(vscode.Uri.file(filePath), diags);
    }
}

// ── WebView Panels ───────────────────────────────────────────────

function showReviewPanel(result: DiffMindReviewResult) {
    const panel = vscode.window.createWebviewPanel(
        'diffmindReview', 'DiffMind Review', vscode.ViewColumn.Two,
        { enableScripts: false }
    );

    let warningHtml = '';
    for (const w of result.warnings) {
        const riskColor = w.risk_level === 'HIGH' ? '#ff4444'
            : w.risk_level === 'MEDIUM' ? '#ffaa00' : '#44cc44';
        const riskBadge = `<span style="background:${riskColor};color:white;padding:2px 8px;border-radius:4px;font-weight:bold;">${w.risk_level}</span>`;

        warningHtml += `
        <div style="border:1px solid #333;border-left:4px solid ${riskColor};padding:16px;margin:12px 0;border-radius:4px;">
            <div style="margin-bottom:8px;">
                ${riskBadge}
                <strong>${w.current_file}</strong>
                <span style="color:#888;margin-left:8px;">${Math.round(w.similarity * 100)}% similar</span>
            </div>
            <div style="color:#ccc;margin:8px 0;">
                <strong>Past bug:</strong> ${w.past_commit} - ${w.past_message}<br>
                <strong>Author:</strong> ${w.past_author} | <strong>Date:</strong> ${w.past_date}
                ${w.is_bugfix ? ' | <span style="color:#ff6666;">BUGFIX</span>' : ''}
            </div>
            <div style="color:#aaa;font-size:13px;margin-top:8px;">${escapeHtml(w.reason)}</div>
        </div>`;
    }

    panel.webview.html = `<!DOCTYPE html>
<html><head><style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; color: #ddd; background: #1e1e1e; }
h1 { color: #fff; border-bottom: 2px solid #555; padding-bottom: 10px; }
.summary { background: #2d2d2d; padding: 16px; border-radius: 8px; margin: 16px 0; }
</style></head><body>
<h1>🔍 DiffMind Review Report</h1>
<div class="summary">
    <strong>Hunks analyzed:</strong> ${result.total_hunks} |
    <strong>Warnings:</strong> ${result.warning_count}
</div>
${warningHtml}
</body></html>`;
}

function showAIReviewPanel(result: AIReviewResult) {
    const panel = vscode.window.createWebviewPanel(
        'diffmindAIReview', 'DiffMind AI Review', vscode.ViewColumn.Two,
        { enableScripts: false }
    );

    let commentsHtml = '';
    for (const c of result.comments) {
        const riskColor = c.risk_level === 'HIGH' ? '#ff4444'
            : c.risk_level === 'MEDIUM' ? '#ffaa00'
                : c.risk_level === 'FALSE_POSITIVE' ? '#44cc44' : '#44cc44';
        const riskBadge = `<span style="background:${riskColor};color:white;padding:2px 8px;border-radius:4px;font-weight:bold;">${c.risk_level}</span>`;

        commentsHtml += `
        <div style="border:1px solid #333;border-left:4px solid ${riskColor};padding:16px;margin:12px 0;border-radius:4px;">
            <div style="margin-bottom:8px;">
                ${riskBadge}
                <strong>${escapeHtml(c.file)}</strong>
                ${c.line_range ? `<span style="color:#888;margin-left:8px;">${c.line_range}</span>` : ''}
                <span style="color:#888;margin-left:8px;">Confidence: ${Math.round(c.confidence * 100)}%</span>
            </div>
            <div style="font-size:15px;margin:8px 0;color:#fff;"><strong>${escapeHtml(c.summary)}</strong></div>
            <div style="color:#ccc;margin:8px 0;">${escapeHtml(c.explanation)}</div>
            ${c.suggestion ? `<div style="color:#88ccff;margin:8px 0;"><strong>💡 Suggestion:</strong> ${escapeHtml(c.suggestion)}</div>` : ''}
            ${c.suggested_code ? `<pre style="background:#2d2d2d;padding:12px;border-radius:4px;overflow-x:auto;"><code>${escapeHtml(c.suggested_code)}</code></pre>` : ''}
            <div style="color:#888;font-size:12px;margin-top:8px;">Past bug: ${escapeHtml(c.past_bug)}</div>
        </div>`;
    }

    const riskEmoji: Record<string, string> = { HIGH: '🔴', MEDIUM: '🟡', LOW: '🟢', CLEAN: '✅' };

    panel.webview.html = `<!DOCTYPE html>
<html><head><style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; padding: 20px; color: #ddd; background: #1e1e1e; }
h1 { color: #fff; border-bottom: 2px solid #555; padding-bottom: 10px; }
.summary { background: #2d2d2d; padding: 16px; border-radius: 8px; margin: 16px 0; }
pre { font-size: 13px; }
code { color: #ce9178; }
</style></head><body>
<h1>✨ DiffMind AI Review</h1>
<div class="summary">
    <strong>Overall Risk:</strong> ${riskEmoji[result.overall_risk] || ''} ${result.overall_risk} |
    <strong>Warnings:</strong> ${result.total_warnings} |
    <strong>False Positives:</strong> ${result.false_positives}<br>
    <strong>Provider:</strong> ${result.provider} (${result.model})
</div>
<div style="background:#1a2a1a;border:1px solid #3a5a3a;padding:12px;border-radius:4px;margin:12px 0;">
    <strong>📋 Summary:</strong> ${escapeHtml(result.summary)}
</div>
${commentsHtml}
</body></html>`;
}

// ── Helpers ──────────────────────────────────────────────────────

function getConfig<T>(key: string): T | undefined {
    return vscode.workspace.getConfiguration('diffmind').get<T>(key);
}

function getWorkspacePath(): string | undefined {
    const folders = vscode.workspace.workspaceFolders;
    if (!folders || folders.length === 0) {
        vscode.window.showErrorMessage('DiffMind: No workspace folder open.');
        return undefined;
    }
    return folders[0].uri.fsPath;
}

function runDiffMind(
    args: string,
    cwd: string,
    timeout: number = 60000
): Promise<string> {
    return new Promise((resolve, reject) => {
        const pythonPath = getConfig<string>('pythonPath') ?? 'python';
        const cmd = `${pythonPath} -m diffmind ${args}`;

        const options: ExecOptions = {
            cwd,
            timeout,
            maxBuffer: 10 * 1024 * 1024,
            env: { ...process.env },
        };

        outputChannel.appendLine(`> ${cmd}`);

        exec(cmd, options, (error, stdout, stderr) => {
            const out = String(stdout || '');
            const err = String(stderr || '');
            if (error) {
                const errMsg = err.trim() || error.message;
                outputChannel.appendLine(`[ERROR] ${errMsg}`);
                reject(new Error(errMsg));
                return;
            }
            if (err.trim()) {
                // Some warnings go to stderr (model loading etc)
                outputChannel.appendLine(`[WARN] ${err.trim()}`);
            }
            resolve(out);
        });
    });
}

function setStatusBar(
    state: 'ready' | 'learning' | 'reviewing' | 'ai-reviewing' | 'clean' | 'warnings' | 'error',
    count?: number
) {
    switch (state) {
        case 'ready':
            statusBarItem.text = '$(shield) DiffMind';
            statusBarItem.tooltip = 'Click to review changes';
            statusBarItem.backgroundColor = undefined;
            break;
        case 'learning':
            statusBarItem.text = '$(sync~spin) DiffMind: Learning...';
            statusBarItem.tooltip = 'Learning from repository history';
            break;
        case 'reviewing':
            statusBarItem.text = '$(sync~spin) DiffMind: Reviewing...';
            statusBarItem.tooltip = 'Reviewing current changes';
            break;
        case 'ai-reviewing':
            statusBarItem.text = '$(sync~spin) DiffMind: AI Analyzing...';
            statusBarItem.tooltip = 'LLM is analyzing warnings';
            break;
        case 'clean':
            statusBarItem.text = '$(check) DiffMind: Clean';
            statusBarItem.tooltip = 'No bug patterns found';
            statusBarItem.backgroundColor = undefined;
            break;
        case 'warnings':
            statusBarItem.text = `$(warning) DiffMind: ${count} warnings`;
            statusBarItem.tooltip = 'Click to review warnings';
            statusBarItem.backgroundColor = new vscode.ThemeColor(
                'statusBarItem.warningBackground'
            );
            break;
        case 'error':
            statusBarItem.text = '$(error) DiffMind: Error';
            statusBarItem.tooltip = 'Check Output panel for details';
            statusBarItem.backgroundColor = new vscode.ThemeColor(
                'statusBarItem.errorBackground'
            );
            break;
    }
}

function debouncedReview() {
    if (saveDebounce) {
        clearTimeout(saveDebounce);
    }
    saveDebounce = setTimeout(() => {
        doReview(false);
    }, 2000);  // 2s debounce
}

function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/\n/g, '<br>');
}
