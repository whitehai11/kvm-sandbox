#include "../authstore.h"

#include <QCoreApplication>
#include <QFile>
#include <QTemporaryDir>

#include <cstdlib>

int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QTemporaryDir directory;
    if (!directory.isValid()) {
        return 1;
    }

    AuthStore store(directory.filePath(QStringLiteral("users.json")));
    if (store.hasUsers() || !store.createFirstUser(QStringLiteral("operator"),
                                                    QStringLiteral("correct horse battery"),
                                                    QStringLiteral("correct horse battery"))) {
        return 2;
    }
    const QFile::Permissions permissions = QFile::permissions(directory.filePath(QStringLiteral("users.json")));
    if (permissions.testFlag(QFileDevice::ReadGroup) || permissions.testFlag(QFileDevice::WriteGroup) ||
        permissions.testFlag(QFileDevice::ReadOther) || permissions.testFlag(QFileDevice::WriteOther)) {
        return 6;
    }
    if (!store.hasUsers() || !store.authenticate(QStringLiteral("operator"),
                                                  QStringLiteral("correct horse battery"))) {
        return 3;
    }
    if (store.authenticate(QStringLiteral("operator"), QStringLiteral("wrong password"))) {
        return 4;
    }
    if (store.createFirstUser(QStringLiteral("second"), QStringLiteral("another password"),
                              QStringLiteral("another password"))) {
        return 5;
    }
    return 0;
}
