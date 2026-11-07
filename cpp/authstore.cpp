#include "authstore.h"

#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSaveFile>

#include <utility>

#include <sodium.h>

AuthStore::AuthStore(QString path) : m_path(std::move(path))
{
    if (sodium_init() < 0) {
        m_lastError = QStringLiteral("libsodium initialization failed");
    }
}

bool AuthStore::load(QJsonObject *users) const
{
    QFile file(m_path);
    if (!file.exists()) {
        *users = {};
        return true;
    }
    if (!file.open(QIODevice::ReadOnly)) {
        m_lastError = QStringLiteral("Cannot open local account store");
        return false;
    }
    const QJsonDocument document = QJsonDocument::fromJson(file.readAll());
    if (!document.isObject() || !document.object().value(QStringLiteral("users")).isObject()) {
        m_lastError = QStringLiteral("Local account store is invalid");
        return false;
    }
    *users = document.object().value(QStringLiteral("users")).toObject();
    return true;
}

bool AuthStore::save(const QJsonObject &users)
{
    QFileInfo info(m_path);
    if (!QDir().mkpath(info.absolutePath())) {
        m_lastError = QStringLiteral("Cannot create local account directory");
        return false;
    }
    QSaveFile file(m_path);
    if (!file.open(QIODevice::WriteOnly)) {
        m_lastError = QStringLiteral("Cannot write local account store");
        return false;
    }
    QJsonObject document;
    document.insert(QStringLiteral("users"), users);
    file.write(QJsonDocument(document).toJson(QJsonDocument::Indented));
    if (!file.commit()) {
        m_lastError = QStringLiteral("Cannot commit local account store");
        return false;
    }
    QFile::setPermissions(m_path, QFileDevice::ReadOwner | QFileDevice::WriteOwner);
    return true;
}

bool AuthStore::validUsername(const QString &username)
{
    static const QRegularExpression pattern(QStringLiteral("^[A-Za-z0-9._-]{3,32}$"));
    return pattern.match(username).hasMatch();
}

bool AuthStore::hasUsers() const
{
    QJsonObject users;
    return load(&users) && !users.isEmpty();
}

bool AuthStore::createFirstUser(const QString &username, const QString &password, const QString &confirmation)
{
    m_lastError.clear();
    QJsonObject users;
    if (!load(&users)) {
        return false;
    }
    if (!users.isEmpty()) {
        m_lastError = QStringLiteral("The first account already exists");
        return false;
    }
    if (!validUsername(username)) {
        m_lastError = QStringLiteral("Username: 3–32 letters, numbers, dot, dash or underscore");
        return false;
    }
    if (password.size() < 12) {
        m_lastError = QStringLiteral("Password must contain at least 12 characters");
        return false;
    }
    if (password != confirmation) {
        m_lastError = QStringLiteral("Passwords do not match");
        return false;
    }
    char encoded[crypto_pwhash_STRBYTES]{};
    const QByteArray passwordBytes = password.toUtf8();
    if (crypto_pwhash_str(encoded, passwordBytes.constData(), passwordBytes.size(),
                          crypto_pwhash_OPSLIMIT_MODERATE, crypto_pwhash_MEMLIMIT_MODERATE) != 0) {
        m_lastError = QStringLiteral("Password hashing failed");
        return false;
    }
    users.insert(username, QString::fromLatin1(encoded));
    return save(users);
}

bool AuthStore::authenticate(const QString &username, const QString &password)
{
    m_lastError.clear();
    QJsonObject users;
    if (!load(&users)) {
        return false;
    }
    const QJsonValue stored = users.value(username);
    const QByteArray passwordBytes = password.toUtf8();
    if (!stored.isString() || crypto_pwhash_str_verify(stored.toString().toLatin1().constData(),
                                                        passwordBytes.constData(), passwordBytes.size()) != 0) {
        m_lastError = QStringLiteral("Invalid username or password");
        return false;
    }
    return true;
}

QString AuthStore::lastError() const
{
    return m_lastError;
}
