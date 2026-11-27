// A small native window for the database manager. It starts the local back end
// (manager/server.py) and shows its interface; closing the window stops the back end.
import Cocoa
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    private var window: NSWindow!
    private var web: WKWebView!
    private var server: Process?

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1320, height: 860),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "EFLM Laboratory Error Database · Manager"
        window.minSize = NSSize(width: 980, height: 620)
        window.center()
        window.setFrameAutosaveName("ManagerWindow")
        web = WKWebView(frame: window.contentView!.bounds, configuration: WKWebViewConfiguration())
        web.autoresizingMask = [.width, .height]
        web.navigationDelegate = self
        web.uiDelegate = self
        window.contentView = web
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        web.loadHTMLString("<body style='font:15px -apple-system;color:#6e6e73;display:grid;place-items:center;height:100vh;margin:0'>Starting…</body>", baseURL: nil)
        startServer()
    }

    private func buildMenu() {
        let main = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Quit Manager", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)
        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "Z")
        edit.addItem(NSMenuItem.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        main.addItem(editItem)
        NSApp.mainMenu = main
    }

    private func fail(_ message: String) {
        DispatchQueue.main.async {
            let alert = NSAlert()
            alert.messageText = "The manager could not start"
            alert.informativeText = message
            alert.runModal()
            NSApp.terminate(nil)
        }
    }

    private func startServer() {
        guard let cfgURL = Bundle.main.url(forResource: "config", withExtension: "json"),
              let data = try? Data(contentsOf: cfgURL),
              let cfg = try? JSONSerialization.jsonObject(with: data) as? [String: String],
              let repo = cfg["repo"], let python = cfg["python"] else {
            return fail("The app has no configuration. Build it again with manager/build_app.sh.")
        }
        let script = repo + "/manager/server.py"
        guard FileManager.default.isExecutableFile(atPath: python), FileManager.default.fileExists(atPath: script) else {
            return fail("The database folder or its Python environment was not found:\n\(repo)\n\nIf the folder was moved, build the app again with manager/build_app.sh.")
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = ["-u", script]
        p.currentDirectoryURL = URL(fileURLWithPath: repo)
        var env = ProcessInfo.processInfo.environment
        // apps started from the Finder get a minimal PATH; git and gh live in these places
        env["PATH"] = [cfg["path"] ?? "", "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", env["PATH"] ?? ""].joined(separator: ":")
        p.environment = env
        let out = Pipe()
        p.standardOutput = out
        p.standardError = out
        do { try p.run() } catch { return fail("Python could not be started: \(error.localizedDescription)") }
        server = p
        DispatchQueue.global().async {
            var buffer = ""
            while p.isRunning || true {
                let chunk = out.fileHandleForReading.availableData
                if chunk.isEmpty { break }
                buffer += String(decoding: chunk, as: UTF8.self)
                if let line = buffer.split(separator: "\n").first(where: { $0.hasPrefix("URL ") }),
                   let url = URL(string: String(line.dropFirst(4))) {
                    DispatchQueue.main.async { self.web.load(URLRequest(url: url)) }
                    return
                }
            }
            self.fail("The back end stopped before it was ready:\n\(buffer.suffix(600))")
        }
    }

    // `Manager --selftest` loads the interface, reports what it shows, and quits (used after a build)
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        guard CommandLine.arguments.contains("--selftest"), webView.url?.host == "127.0.0.1" else { return }
        DispatchQueue.main.asyncAfter(deadline: .now() + 12) {
            let js = "document.querySelector('.places') ? 'OK: ' + [...document.querySelectorAll('.card .big')].map(e => e.textContent).join(' | ') : 'NOT READY: ' + document.body.innerText.slice(0, 300)"
            webView.evaluateJavaScript(js) { result, error in
                print("SELFTEST", result ?? error?.localizedDescription ?? "no result")
                NSApp.terminate(nil)
            }
        }
    }

    func applicationWillTerminate(_ notification: Notification) { server?.terminate() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    // links to GitHub and the website open in the default browser, not inside the app
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, let host = url.host, host != "127.0.0.1", url.scheme?.hasPrefix("http") == true {
            NSWorkspace.shared.open(url)
            return decisionHandler(.cancel)
        }
        decisionHandler(.allow)
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { NSWorkspace.shared.open(url) }
        return nil
    }
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert(); alert.messageText = message; alert.runModal(); completionHandler()
    }
    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert(); alert.messageText = message
        alert.addButton(withTitle: "OK"); alert.addButton(withTitle: "Cancel")
        completionHandler(alert.runModal() == .alertFirstButtonReturn)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
