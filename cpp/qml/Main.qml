import QtQuick 6.5
import QtQuick.Controls 6.5
import QtQuick.Controls.Material 6.5
import QtQuick.Layouts 6.5
import QtQuick.Dialogs 6.5

ApplicationWindow {
    id: window
    visible: true
    width: 1180
    height: 760
    minimumWidth: 980
    minimumHeight: 640
    title: "KVM Sandbox"
    color: palette.window

    Material.theme: Material.Dark
    Material.accent: Material.Cyan

    property color ink: "#f4f7fb"
    property color muted: "#8d99aa"
    property color panel: "#171d27"
    property color panelRaised: "#1d2633"
    property color line: "#2a3545"
    property color cyan: "#61e7e1"
    property color amber: "#f0bd73"

    function notify(message) {
        statusText.text = message
    }

    Connections {
        target: backend
        function onActivityChanged() { statusText.text = backend.activity }
    }

    Dialog {
        id: destroyDialog
        title: "Destroy disposable VM"
        modal: true
        standardButtons: Dialog.Yes | Dialog.No
        anchors.centerIn: parent
        contentItem: Label {
            padding: 22
            text: "Destroy " + backend.selectedSession + "? Evidence stays on disk."
            color: window.ink
            wrapMode: Text.WordWrap
        }
        onAccepted: backend.destroySelected()
    }

    Loader {
        anchors.fill: parent
        sourceComponent: backend.loggedIn ? dashboard : login
    }

    Component {
        id: login
        Rectangle {
            color: "#0d1118"

            Rectangle {
                anchors.centerIn: parent
                width: 460
                height: backend.firstRun ? 520 : 430
                radius: 14
                color: window.panel
                border.color: window.line
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 34
                    spacing: 16

                    Label {
                        text: "KVM // CONTROL"
                        color: window.cyan
                        font.pixelSize: 13
                        font.letterSpacing: 2
                        font.bold: true
                    }
                    Label {
                        text: backend.firstRun ? "Create local operator account" : "Sign in to your sandbox"
                        color: window.ink
                        font.pixelSize: 26
                        font.bold: true
                    }
                    Label {
                        text: "A local control plane for disposable virtual machines."
                        color: window.muted
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Item { Layout.preferredHeight: 6 }
                    TextField { id: user; Layout.fillWidth: true; placeholderText: "Username"; selectByMouse: true }
                    TextField { id: password; Layout.fillWidth: true; placeholderText: "Password"; echoMode: TextInput.Password; selectByMouse: true }
                    TextField {
                        id: confirmation
                        visible: backend.firstRun
                        Layout.fillWidth: true
                        placeholderText: "Confirm password"
                        echoMode: TextInput.Password
                        selectByMouse: true
                    }
                    Label {
                        id: error
                        text: backend.activity
                        color: "#ff9b9b"
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    Button {
                        Layout.fillWidth: true
                        text: backend.firstRun ? "Create account" : "Sign in"
                        highlighted: true
                        onClicked: {
                            const ok = backend.firstRun
                                ? backend.createAccount(user.text, password.text, confirmation.text)
                                : backend.login(user.text, password.text)
                            if (!ok) error.text = backend.activity
                        }
                    }
                    Label {
                        text: "Local only · passwords stored as Argon2id hashes"
                        color: window.muted
                        font.pixelSize: 12
                        Layout.alignment: Qt.AlignHCenter
                    }
                }
            }
        }
    }

    Component {
        id: dashboard
        Rectangle {
            color: "#0d1118"

            RowLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    Layout.fillHeight: true
                    Layout.preferredWidth: 240
                    color: "#10161f"
                    border.color: window.line
                    border.width: 1

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 22
                        spacing: 8
                        Label { text: "KVM / SANDBOX"; color: window.cyan; font.bold: true; font.letterSpacing: 1.5 }
                        Label { text: "control plane"; color: window.muted; font.pixelSize: 12 }
                        Item { Layout.preferredHeight: 24 }
                        Label { text: "WORKSPACE"; color: window.muted; font.pixelSize: 11; font.bold: true }
                        Rectangle { Layout.fillWidth: true; height: 42; radius: 8; color: window.panelRaised; border.color: window.line
                            RowLayout { anchors.fill: parent; anchors.margins: 12; Label { text: "▦"; color: window.cyan; font.pixelSize: 17 } Label { text: "Overview"; color: window.ink; font.bold: true } }
                        }
                        Rectangle { Layout.fillWidth: true; height: 42; radius: 8; color: "transparent"
                            RowLayout { anchors.fill: parent; anchors.margins: 12; Label { text: "▣"; color: window.muted; font.pixelSize: 17 } Label { text: "Virtual machines"; color: window.muted } }
                        }
                        Item { Layout.fillHeight: true }
                        Label { text: "SECURITY POSTURE"; color: window.muted; font.pixelSize: 11; font.bold: true }
                        Label { text: "●  vTPM 2.0"; color: window.cyan }
                        Label { text: "●  UEFI Secure Boot"; color: window.cyan }
                        Label { text: "●  no host sharing"; color: window.cyan }
                        Item { Layout.preferredHeight: 16 }
                        Button { text: "Sign out"; Layout.fillWidth: true; onClicked: backend.logout() }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    anchors.margins: 30
                    spacing: 22

                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: "Overview"; color: window.ink; font.pixelSize: 28; font.bold: true }
                        Item { Layout.fillWidth: true }
                        Label { text: backend.currentUser; color: window.muted }
                        Button { text: "↻"; onClicked: backend.refresh() }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 126
                        radius: 12
                        color: window.panel
                        border.color: window.line
                        RowLayout {
                            anchors.fill: parent; anchors.margins: 22; spacing: 18
                            ColumnLayout { Layout.fillWidth: true; Label { text: "Disposable Windows environment"; color: window.ink; font.pixelSize: 19; font.bold: true } Label { text: "Create a clean QCOW2 overlay from the sealed baseline."; color: window.muted } }
                            Button { text: "Create VM"; highlighted: true; enabled: !backend.busy; onClicked: backend.createVm() }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 88
                        Repeater {
                            model: [
                                {label: "vTPM", value: "2.0", color: window.cyan},
                                {label: "Firmware", value: "Secure Boot", color: window.cyan},
                                {label: "Network", value: "Isolated", color: window.amber},
                                {label: "Sessions", value: backend.sessions.length, color: window.ink}
                            ]
                            delegate: Rectangle {
                                Layout.fillWidth: true; Layout.fillHeight: true; radius: 10; color: window.panel; border.color: window.line
                                ColumnLayout { anchors.fill: parent; anchors.margins: 16; Label { text: modelData.label; color: window.muted; font.pixelSize: 12 } Label { text: modelData.value; color: modelData.color; font.pixelSize: 18; font.bold: true } }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 18

                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 3; radius: 12; color: window.panel; border.color: window.line
                            ColumnLayout { anchors.fill: parent; anchors.margins: 20; spacing: 12
                                RowLayout {
                                    Layout.fillWidth: true
                                    Label { text: "Disposable VMs"; color: window.ink; font.pixelSize: 17; font.bold: true }
                                    Item { Layout.fillWidth: true }
                                    Button { text: "Refresh"; onClicked: backend.refresh() }
                                }
                                Label { visible: backend.sessions.length === 0; text: "No sessions yet. Create a VM to begin."; color: window.muted; Layout.fillWidth: true; Layout.topMargin: 20 }
                                ListView { id: vmList; Layout.fillWidth: true; Layout.fillHeight: true; clip: true; model: backend.sessions; spacing: 8
                                    delegate: Rectangle { width: vmList.width; height: 72; radius: 9; color: backend.selectedSession === modelData.id ? "#20343c" : window.panelRaised; border.color: backend.selectedSession === modelData.id ? window.cyan : window.line
                                        MouseArea { anchors.fill: parent; onClicked: backend.selectedSession = modelData.id }
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.margins: 14
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                Label { text: modelData.id; color: window.ink; font.bold: true }
                                                Label { text: modelData.vmName; color: window.muted; font.pixelSize: 12 }
                                            }
                                            Label { text: "›"; color: window.cyan; font.pixelSize: 22 }
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Button { text: "Stop"; enabled: backend.selectedSession.length > 0 && !backend.busy; onClicked: backend.stopSelected() }
                                    Button { text: "Destroy"; enabled: backend.selectedSession.length > 0 && !backend.busy; onClicked: destroyDialog.open() }
                                    Item { Layout.fillWidth: true }
                                    Label { text: backend.selectedSession.length > 0 ? "Selected" : "Nothing selected"; color: window.muted }
                                }
                            }
                        }

                        Rectangle {
                            Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 2; radius: 12; color: window.panel; border.color: window.line
                            ColumnLayout { anchors.fill: parent; anchors.margins: 20; spacing: 14
                                Label { text: "Baseline image"; color: window.ink; font.pixelSize: 17; font.bold: true }
                                Label { text: "Install once, seal once, clone clean overlays."; color: window.muted; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                                Repeater { model: backend.baseline; delegate: Label { text: "✓  " + modelData; color: window.ink; font.pixelSize: 13 } }
                                Item { Layout.fillHeight: true }
                                Button { text: "Initialize host layout"; enabled: !backend.busy; onClicked: backend.initialize() }
                                Button { text: "Create base VM"; enabled: !backend.busy; onClicked: backend.createBaseVm() }
                                Button { text: "Seal base image"; enabled: !backend.busy; onClicked: backend.sealBase() }
                            }
                        }
                    }

                    Label { id: statusText; text: backend.activity || "Ready"; color: window.muted; elide: Text.ElideRight; Layout.fillWidth: true }
                }
            }
        }
    }
}
