import Cocoa
import UserNotifications
import Foundation

struct BriefingData: Decodable {
    struct CalendarEvent: Decodable {
        let time: String
        let title: String
        let attendees: [String]
        let zoom: Bool
    }
    struct LinearIssue: Decodable {
        let id: String
        let title: String
        let status: String
        let due: String
    }
    struct NotionPage: Decodable {
        let title: String
    }
    struct SlackSave: Decodable {
        let channel: String
        let user: String
        let text: String
    }

    let targetLabel: String?
    let targetDisplay: String?
    let calendar: [CalendarEvent]
    let linear: [LinearIssue]
    let notion: [NotionPage]
    let slack: [SlackSave]
    let conflicts: [String]?
    let errors: [String]?

    enum CodingKeys: String, CodingKey {
        case targetLabel = "target_label"
        case targetDisplay = "target_display"
        case calendar, linear, notion, slack, conflicts, errors
    }
}

let VIEW_ACTION = "VIEW_BRIEFING"
let CATEGORY_ID = "DAILY_BRIEFING"

class AppDelegate: NSObject, NSApplicationDelegate, UNUserNotificationCenterDelegate {
    var projectDir: URL!
    var launchedFromNotification = false

    func applicationDidFinishLaunching(_ notification: Notification) {
        let center = UNUserNotificationCenter.current()
        center.delegate = self

        let viewAction = UNNotificationAction(
            identifier: VIEW_ACTION,
            title: "View Full Briefing",
            options: [.foreground]
        )
        let category = UNNotificationCategory(
            identifier: CATEGORY_ID,
            actions: [viewAction],
            intentIdentifiers: [],
            options: []
        )
        center.setNotificationCategories([category])

        if notification.userInfo?[NSApplication.launchUserNotificationUserInfoKey] is UNNotificationResponse {
            launchedFromNotification = true
            openBriefingHTML()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                NSApplication.shared.terminate(nil)
            }
            return
        }

        center.requestAuthorization(options: [.alert, .sound]) { granted, error in
            if let error = error {
                fputs("Authorization error: \(error.localizedDescription)\n", stderr)
                self.quit()
                return
            }
            if !granted {
                fputs("Notification permission denied.\n", stderr)
                self.quit()
                return
            }
            self.clearAndSend()
        }
    }

    func clearAndSend() {
        let center = UNUserNotificationCenter.current()
        center.removeAllDeliveredNotifications()
        center.removeAllPendingNotificationRequests()

        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            self.sendNotification()
        }
    }

    func sendNotification() {
        let jsonURL = projectDir.appendingPathComponent("briefing.json")
        guard let jsonData = try? Data(contentsOf: jsonURL),
              let briefing = try? JSONDecoder().decode(BriefingData.self, from: jsonData) else {
            fputs("Failed to read or parse \(jsonURL.path)\n", stderr)
            quit()
            return
        }

        let label = briefing.targetLabel ?? "Tomorrow"
        let dateStr = briefing.targetDisplay ?? ""

        let content = UNMutableNotificationContent()
        content.title = "\(label) — \(dateStr)"
        content.sound = .default
        content.categoryIdentifier = CATEGORY_ID

        var parts: [String] = []
        if !briefing.calendar.isEmpty { parts.append("\(briefing.calendar.count) meeting\(briefing.calendar.count == 1 ? "" : "s")") }
        if !briefing.linear.isEmpty { parts.append("\(briefing.linear.count) deadline\(briefing.linear.count == 1 ? "" : "s")") }
        if !briefing.notion.isEmpty { parts.append("\(briefing.notion.count) Notion update\(briefing.notion.count == 1 ? "" : "s")") }
        if !briefing.slack.isEmpty { parts.append("\(briefing.slack.count) Slack save\(briefing.slack.count == 1 ? "" : "s")") }
        content.body = parts.isEmpty ? "Nothing on the radar" : parts.joined(separator: " · ")

        let request = UNNotificationRequest(
            identifier: "daily-briefing",
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                fputs("Failed: \(error.localizedDescription)\n", stderr)
            } else {
                fputs("Notification delivered.\n", stderr)
            }
            self.quit()
        }
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        completionHandler([.banner, .sound, .list])
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        if !launchedFromNotification {
            openBriefingHTML()
        }
        completionHandler()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            NSApplication.shared.terminate(nil)
        }
    }

    func openBriefingHTML() {
        let htmlURL = projectDir.appendingPathComponent("briefing.html")
        if FileManager.default.fileExists(atPath: htmlURL.path) {
            NSWorkspace.shared.open(htmlURL)
        } else {
            fputs("briefing.html not found at \(htmlURL.path)\n", stderr)
        }
    }

    func quit() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            NSApplication.shared.terminate(nil)
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()

let bundlePath = Bundle.main.bundlePath
delegate.projectDir = URL(fileURLWithPath: bundlePath).deletingLastPathComponent()

app.delegate = delegate
app.run()
