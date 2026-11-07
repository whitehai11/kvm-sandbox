#include "backend.h"

#include <QGuiApplication>
#include <QDebug>
#include <QUrl>
#include <QQmlApplicationEngine>
#include <QQmlComponent>
#include <QQmlContext>

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);
    QGuiApplication::setApplicationName(QStringLiteral("KVM Sandbox"));
    QGuiApplication::setOrganizationName(QStringLiteral("Local Sandbox"));

    Backend backend;
    QQmlApplicationEngine engine;
    QObject::connect(&engine, &QQmlApplicationEngine::warnings, [](const QList<QQmlError> &warnings) {
        for (const QQmlError &warning : warnings) {
            qWarning().noquote() << warning.toString();
        }
    });
    QObject::connect(&engine, &QQmlApplicationEngine::objectCreationFailed,
                     [](const QUrl &url) { qWarning().noquote() << "QML object creation failed:" << url; });
    engine.rootContext()->setContextProperty(QStringLiteral("backend"), &backend);
    const QUrl qmlUrl(QStringLiteral("qrc:/qt/qml/KvmSandbox/qml/Main.qml"));
    QQmlComponent component(&engine, qmlUrl);
    QObject *root = component.create(engine.rootContext());
    for (const QQmlError &error : component.errors()) {
        qWarning().noquote() << error.toString();
    }
    if (root == nullptr) {
        return 1;
    }
    return app.exec();
}
