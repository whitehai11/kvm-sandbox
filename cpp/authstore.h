#pragma once

#include <QString>
#include <QJsonObject>

class AuthStore final {
public:
    explicit AuthStore(QString path);

    bool hasUsers() const;
    bool createFirstUser(const QString &username, const QString &password, const QString &confirmation);
    bool authenticate(const QString &username, const QString &password);
    QString lastError() const;

private:
    bool load(QJsonObject *users) const;
    bool save(const QJsonObject &users);
    static bool validUsername(const QString &username);

    QString m_path;
    mutable QString m_lastError;
};
