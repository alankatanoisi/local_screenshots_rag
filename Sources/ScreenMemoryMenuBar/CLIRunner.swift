import Foundation

struct CLIRunner {
    // The app is development-focused for now, so we keep the repo root explicit and easy to inspect.
    static let defaultProjectRoot = "/Users/alanman/Documents/local_screenshots_rag"

    private func projectRoot() -> String {
        ProcessInfo.processInfo.environment["SCREENMEMORY_PROJECT_ROOT"] ?? Self.defaultProjectRoot
    }

    private func executableAndArguments(extraArguments: [String]) -> (String, [String]) {
        let root = projectRoot()
        let venvPython = "\(root)/.venv/bin/python"

        if FileManager.default.isExecutableFile(atPath: venvPython) {
            return (venvPython, ["-m", "screenmemory"] + extraArguments)
        }

        return (
            "/opt/homebrew/bin/uv",
            ["run", "--directory", root, "python", "-m", "screenmemory"] + extraArguments
        )
    }

    private func runCommand(arguments: [String]) throws -> Data {
        // We spawn the Python CLI as a child process and read its JSON from standard output.
        let process = Process()
        let outputPipe = Pipe()
        let errorPipe = Pipe()
        let command = executableAndArguments(extraArguments: arguments)
        let root = projectRoot()

        process.executableURL = URL(fileURLWithPath: command.0)
        process.arguments = command.1
        process.currentDirectoryURL = URL(fileURLWithPath: root)

        // Point Python directly at the source tree so the app does not depend on a fragile
        // console-script wrapper or editable-install metadata surviving folder renames.
        var environment = ProcessInfo.processInfo.environment
        let srcPath = "\(root)/src"
        if let existing = environment["PYTHONPATH"], !existing.isEmpty {
            environment["PYTHONPATH"] = "\(srcPath):\(existing)"
        } else {
            environment["PYTHONPATH"] = srcPath
        }
        process.environment = environment

        process.standardOutput = outputPipe
        process.standardError = errorPipe

        try process.run()
        process.waitUntilExit()

        let stdout = outputPipe.fileHandleForReading.readDataToEndOfFile()
        let stderr = errorPipe.fileHandleForReading.readDataToEndOfFile()

        guard process.terminationStatus == 0 else {
            let message = String(data: stderr, encoding: .utf8) ?? "Unknown CLI error."
            throw NSError(
                domain: "ScreenMemoryCLI",
                code: Int(process.terminationStatus),
                userInfo: [NSLocalizedDescriptionKey: message]
            )
        }

        return stdout
    }

    func fetchStatus() throws -> StatusDTO {
        let data = try runCommand(arguments: ["status", "--json"])
        return try JSONDecoder().decode(StatusDTO.self, from: data)
    }

    func search(
        query: String,
        mode: QueryMode,
        limit: Int = 8
    ) throws -> SearchResponseDTO {
        let data = try runCommand(
            arguments: [
                "query",
                query,
                "--mode",
                mode.rawValue,
                "--limit",
                String(limit),
                "--json",
            ]
        )
        return try JSONDecoder().decode(SearchResponseDTO.self, from: data)
    }
}
