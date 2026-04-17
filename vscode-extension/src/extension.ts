import * as vscode from "vscode";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { spawnSync, execFileSync, ExecFileSyncOptions } from "child_process";

// ── Extension lifecycle ──────────────────────────────────────────────────────

export function activate(ctx: vscode.ExtensionContext): void {
  ctx.subscriptions.push(
    vscode.commands.registerCommand(
      "dbcdiff.showDiffFromHead",
      (uri?: vscode.Uri) => showDiffFromHead(uri)
    ),
    vscode.commands.registerCommand(
      "dbcdiff.comparePick",
      (uri?: vscode.Uri) => showDiffPick(uri)
    )
  );
}

export function deactivate(): void {}

// ── Commands ─────────────────────────────────────────────────────────────────

/** Compare the current .dbc file against its HEAD (git) version. */
async function showDiffFromHead(uri?: vscode.Uri): Promise<void> {
  const fileUri = resolveUri(uri);
  if (!fileUri) return;

  const ws = vscode.workspace.getWorkspaceFolder(fileUri);
  if (!ws) {
    vscode.window.showErrorMessage("File must be inside a workspace folder.");
    return;
  }

  // Relative path with forward slashes for git show
  const relPath = path
    .relative(ws.uri.fsPath, fileUri.fsPath)
    .replace(/\\/g, "/");

  // Retrieve HEAD content via `git show HEAD:<relPath>`
  const gitResult = spawnSync("git", ["show", `HEAD:${relPath}`], {
    cwd: ws.uri.fsPath,
    maxBuffer: 20 * 1024 * 1024,
  });

  if (gitResult.status !== 0) {
    vscode.window.showInformationMessage(
      "No HEAD version found for this file. " +
        'Is it tracked by git? Use "DBC: Compare with…" for untracked files.'
    );
    return;
  }

  // Write HEAD content to a temp file for comparison
  const tmpBase = path.join(
    os.tmpdir(),
    `dbcdiff_base_${Date.now()}_${path.basename(fileUri.fsPath)}`
  );

  try {
    fs.writeFileSync(tmpBase, gitResult.stdout as Buffer);
    await runAndShowReport(
      tmpBase,
      fileUri.fsPath,
      `${path.basename(fileUri.fsPath)} — semantic diff vs HEAD`
    );
  } finally {
    try {
      fs.rmSync(tmpBase, { force: true });
    } catch {}
  }
}

/** Compare the current .dbc file against another .dbc chosen by the user. */
async function showDiffPick(uri?: vscode.Uri): Promise<void> {
  const fileUri = resolveUri(uri);
  if (!fileUri) return;

  const picks = await vscode.window.showOpenDialog({
    canSelectMany: false,
    filters: { "DBC files": ["dbc"] },
    title: "Select the reference DBC file",
  });
  if (!picks?.length) return;

  await runAndShowReport(
    picks[0].fsPath,
    fileUri.fsPath,
    `${path.basename(picks[0].fsPath)} → ${path.basename(fileUri.fsPath)}`
  );
}

// ── Core diff logic ───────────────────────────────────────────────────────────

async function runAndShowReport(
  basePath: string,
  headPath: string,
  title: string
): Promise<void> {
  const python = getPythonPath();
  const suffix = Date.now();
  const htmlTmp = path.join(os.tmpdir(), `dbcdiff_report_${suffix}.html`);
  const jsonTmp = path.join(os.tmpdir(), `dbcdiff_report_${suffix}.json`);

  // Run dbcdiff inside a progress notification
  await vscode.window.withProgress(
    {
      location: vscode.ProgressLocation.Notification,
      title: "DBC diff: comparing…",
      cancellable: false,
    },
    async () => {
      try {
        const opts: ExecFileSyncOptions = {
          encoding: "utf8",
          timeout: 30_000,
        };
        execFileSync(
          python,
          [
            "-m",
            "dbcdiff",
            basePath,
            headPath,
            "--html-out",
            htmlTmp,
            "--json-out",
            jsonTmp,
            "--no-color",
          ],
          opts
        );
      } catch (err: unknown) {
        // dbcdiff exits non-zero for any detected difference — that is expected.
        // We only treat it as a real error when the HTML output is absent.
        if (!fs.existsSync(htmlTmp)) {
          const msg =
            `dbcdiff failed to produce a report.\n` +
            `Make sure it is installed:\n  ${python} -m pip install dbcdiff`;
          vscode.window.showErrorMessage(msg);
          return;
        }
      }
    }
  );

  if (!fs.existsSync(htmlTmp)) return;

  // Show the HTML report in a Webview panel beside the editor
  const panel = vscode.window.createWebviewPanel(
    "dbcdiffReport",
    `🚗  ${title}`,
    vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true }
  );

  panel.webview.html = fs.readFileSync(htmlTmp, "utf8");

  // Clean up temp files when the panel is closed
  panel.onDidDispose(() => {
    for (const f of [htmlTmp, jsonTmp]) {
      try {
        fs.rmSync(f, { force: true });
      } catch {}
    }
  });

  // Show a severity notification in the status area
  if (fs.existsSync(jsonTmp)) {
    try {
      showSeverityNotification(jsonTmp);
    } catch {}
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function resolveUri(uri?: vscode.Uri): vscode.Uri | undefined {
  const result =
    uri ?? vscode.window.activeTextEditor?.document.uri;

  if (!result) {
    vscode.window.showWarningMessage(
      "No active editor found. Open a .dbc file first."
    );
    return undefined;
  }
  if (path.extname(result.fsPath).toLowerCase() !== ".dbc") {
    vscode.window.showWarningMessage("Please select or open a .dbc file.");
    return undefined;
  }
  return result;
}

function getPythonPath(): string {
  return (
    vscode.workspace
      .getConfiguration("dbcdiff")
      .get<string>("pythonPath") ?? "python"
  );
}

/** Parse the JSON report and display a colour-coded notification. */
function showSeverityNotification(jsonPath: string): void {
  const data = JSON.parse(fs.readFileSync(jsonPath, "utf8"));
  const s = (data?.summary ?? {}) as Record<string, number>;

  const breaking   = s.breaking   ?? 0;
  const functional = s.functional ?? 0;
  const metadata   = s.metadata   ?? 0;

  if (breaking > 0) {
    vscode.window.showErrorMessage(
      `DBC diff: 🔴 ${breaking} BREAKING change(s) detected.`
    );
  } else if (functional > 0) {
    vscode.window.showWarningMessage(
      `DBC diff: 🟠 ${functional} functional change(s).`
    );
  } else if (metadata > 0) {
    vscode.window.showInformationMessage(
      `DBC diff: 🟡 ${metadata} metadata change(s).`
    );
  } else {
    vscode.window.showInformationMessage(
      "DBC diff: 🟢 Files are semantically identical."
    );
  }
}
