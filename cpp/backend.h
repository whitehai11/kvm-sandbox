#pragma once

#include "authstore.h"

#include <QProcess>
#include <QStringList>
#include <QVariantList>

class Backend final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool loggedIn READ loggedIn NOTIFY loggedInChanged)
    Q_PROPERTY(bool firstRun READ firstRun NOTIFY firstRunChanged)
    Q_PROPERTY(bool busy READ busy NOTIFY busyChanged)
    Q_PROPERTY(QString currentUser READ currentUser NOTIFY currentUserChanged)
    Q_PROPERTY(QString selectedSession READ selectedSession WRITE setSelectedSession NOTIFY selectedSessionChanged)
    Q_PROPERTY(QVariantList sessions READ sessions NOTIFY sessionsChanged)
    Q_PROPERTY(QStringList baseline READ baseline CONSTANT)
    Q_PROPERTY(QString activity READ activity NOTIFY activityChanged)

public:
    explicit Backend(QObject *parent = nullptr);

    bool loggedIn() const { return m_loggedIn; }
    bool firstRun() const { return m_firstRun; }
    bool busy() const { return m_process.state() != QProcess::NotRunning; }
    QString currentUser() const { return m_currentUser; }
    QString selectedSession() const { return m_selectedSession; }
    QVariantList sessions() const { return m_sessions; }
    QStringList baseline() const;
    QString activity() const { return m_activity; }

    void setSelectedSession(const QString &session);

    Q_INVOKABLE bool createAccount(const QString &username, const QString &password, const QString &confirmation);
    Q_INVOKABLE bool login(const QString &username, const QString &password);
    Q_INVOKABLE void logout();
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void initialize();
    Q_INVOKABLE void createBaseVm();
    Q_INVOKABLE void sealBase();
    Q_INVOKABLE void createVm();
    Q_INVOKABLE void stopSelected();
    Q_INVOKABLE void destroySelected();

signals:
    void loggedInChanged();
    void firstRunChanged();
    void busyChanged();
    void currentUserChanged();
    void selectedSessionChanged();
    void sessionsChanged();
    void activityChanged();

private slots:
    void processFinished(int exitCode, QProcess::ExitStatus exitStatus);

private:
    void setActivity(const QString &message);
    void startCommand(const QStringList &arguments);
    void loadSessions();
    QString projectDir() const;
    QString configPath() const;
    QString scriptPath() const;

    AuthStore m_auth;
    QProcess m_process;
    QVariantList m_sessions;
    QString m_selectedSession;
    QString m_currentUser;
    QString m_activity;
    bool m_loggedIn = false;
    bool m_firstRun = false;
    int m_failedLogins = 0;
    qint64 m_retryAfterMs = 0;
};
