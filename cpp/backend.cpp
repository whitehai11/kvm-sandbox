#include "backend.h"

#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QStandardPaths>

#include <utility>

namespace {
QString accountPath()
{
    const QString dir = QStandardPaths::writableLocation(QStandardPaths::AppConfigLocation);
    return QDir(dir).filePath(QStringLiteral("users.json"));
}
}

Backend::Backend(QObject *parent)
    : QObject(parent), m_auth(accountPath())
{
    connect(&m_process, &QProcess::finished, this, &Backend::processFinished);
    connect(&m_process, &QProcess::stateChanged, this, [this] { emit busyChanged(); });
    m_firstRun = !m_auth.hasUsers();
    loadSessions();
}

QStringList Backend::baseline() const
{
    return {
        QStringLiteral("Python 3"),
        QStringLiteral(".NET Desktop Runtime"),
        QStringLiteral("Microsoft Visual C++ Redistributables"),
        QStringLiteral("7-Zip"),
        QStringLiteral("Firefox"),
        QStringLiteral("Chrome"),
        QStringLiteral("Discord"),
        QStringLiteral("reviewed test game build"),
    };
}

void Backend::setActivity(const QString &message)
{
    m_activity = message;
    emit activityChanged();
}

bool Backend::createAccount(const QString &username, const QString &password, const QString &confirmation)
{
    if (!m_firstRun) {
        setActivity(QStringLiteral("Local account setup is already complete"));
        return false;
    }
    if (!m_auth.createFirstUser(username, password, confirmation)) {
        setActivity(m_auth.lastError());
        return false;
    }
    m_firstRun = false;
    m_loggedIn = true;
    m_currentUser = username;
    emit firstRunChanged();
    emit loggedInChanged();
    emit currentUserChanged();
    setActivity(QStringLiteral("Account created · local session active"));
    return true;
}

bool Backend::login(const QString &username, const QString &password)
{
    const qint64 now = QDateTime::currentMSecsSinceEpoch();
    if (now < m_retryAfterMs) {
        setActivity(QStringLiteral("Too many attempts · try again in a moment"));
        return false;
    }
    if (!m_auth.authenticate(username, password)) {
        ++m_failedLogins;
        if (m_failedLogins >= 5) {
            m_retryAfterMs = now + 5000;
            m_failedLogins = 0;
        }
        setActivity(m_auth.lastError());
        return false;
    }
    m_failedLogins = 0;
    m_loggedIn = true;
    m_currentUser = username;
    emit loggedInChanged();
    emit currentUserChanged();
    setActivity(QStringLiteral("Local session active"));
    return true;
}

void Backend::logout()
{
    m_loggedIn = false;
    m_currentUser.clear();
    emit loggedInChanged();
    emit currentUserChanged();
    setActivity(QStringLiteral("Signed out"));
}

QString Backend::projectDir() const
{
    const QByteArray configured = qgetenv("KVM_SANDBOX_ROOT");
    return configured.isEmpty() ? QStringLiteral(SANDBOX_PROJECT_DIR) : QString::fromUtf8(configured);
}

QString Backend::configPath() const
{
    return QDir(projectDir()).filePath(QStringLiteral("config.toml"));
}

QString Backend::scriptPath() const
{
    return QDir(projectDir()).filePath(QStringLiteral("sandboxctl.py"));
}

void Backend::startCommand(const QStringList &arguments)
{
    if (!m_loggedIn) {
        setActivity(QStringLiteral("Sign in first"));
        return;
    }
    if (busy()) {
        setActivity(QStringLiteral("Another operation is still running"));
        return;
    }
    if (!QFile::exists(scriptPath())) {
        setActivity(QStringLiteral("sandboxctl.py not found under KVM_SANDBOX_ROOT"));
        return;
    }
    QStringList command = {scriptPath(), QStringLiteral("--config"), configPath()};
    command.append(arguments);
    setActivity(QStringLiteral("Running %1").arg(arguments.join(QLatin1Char(' '))));
    m_process.setProgram(QStringLiteral("python3"));
    m_process.setArguments(command);
    m_process.start();
}

void Backend::processFinished(int exitCode, QProcess::ExitStatus exitStatus)
{
    const QString output = QString::fromUtf8(m_process.readAllStandardOutput() + m_process.readAllStandardError()).trimmed();
    if (exitStatus != QProcess::NormalExit || exitCode != 0) {
        setActivity(output.isEmpty() ? QStringLiteral("Operation failed") : output);
        return;
    }
    setActivity(output.isEmpty() ? QStringLiteral("Operation complete") : output);
    loadSessions();
}

void Backend::loadSessions()
{
    QVariantList next;
    const QDir evidence(QDir(projectDir()).filePath(QStringLiteral("evidence")));
    static const QRegularExpression idPattern(QStringLiteral("^s-\\d{8}T\\d{6}Z-[0-9a-f]{8}$"));
    const QFileInfoList dirs = evidence.entryInfoList(QDir::Dirs | QDir::NoDotAndDotDot, QDir::Name);
    for (const QFileInfo &dir : dirs) {
        QFile file(QDir(dir.absoluteFilePath()).filePath(QStringLiteral("session.json")));
        if (!file.open(QIODevice::ReadOnly)) {
            continue;
        }
        const QJsonObject object = QJsonDocument::fromJson(file.readAll()).object();
        const QString id = object.value(QStringLiteral("session_id")).toString();
        const QString vmName = object.value(QStringLiteral("vm_name")).toString();
        if (!idPattern.match(id).hasMatch() || vmName != QStringLiteral("win11-") + id) {
            continue;
        }
        next.append(QVariantMap{{QStringLiteral("id"), id},
                                {QStringLiteral("vmName"), vmName},
                                {QStringLiteral("uuid"), object.value(QStringLiteral("hardware_uuid")).toString()}});
    }
    m_sessions = next;
    if (!m_selectedSession.isEmpty()) {
        bool stillPresent = false;
        for (const QVariant &value : std::as_const(m_sessions)) {
            if (value.toMap().value(QStringLiteral("id")).toString() == m_selectedSession) {
                stillPresent = true;
                break;
            }
        }
        if (!stillPresent) {
            m_selectedSession.clear();
            emit selectedSessionChanged();
        }
    }
    emit sessionsChanged();
}

void Backend::setSelectedSession(const QString &session)
{
    if (m_selectedSession == session) {
        return;
    }
    m_selectedSession = session;
    emit selectedSessionChanged();
}

void Backend::refresh()
{
    loadSessions();
    setActivity(QStringLiteral("Session list refreshed"));
}

void Backend::initialize() { startCommand({QStringLiteral("init")}); }
void Backend::createBaseVm() { startCommand({QStringLiteral("base-install")}); }
void Backend::sealBase() { startCommand({QStringLiteral("base-seal")}); }
void Backend::createVm() { startCommand({QStringLiteral("session-start"), QStringLiteral("--sample"), QStringLiteral("ui-created")}); }

void Backend::stopSelected()
{
    if (m_selectedSession.isEmpty()) {
        setActivity(QStringLiteral("Select a VM first"));
        return;
    }
    startCommand({QStringLiteral("session-stop"), m_selectedSession});
}

void Backend::destroySelected()
{
    if (m_selectedSession.isEmpty()) {
        setActivity(QStringLiteral("Select a VM first"));
        return;
    }
    startCommand({QStringLiteral("session-destroy"), m_selectedSession});
}
