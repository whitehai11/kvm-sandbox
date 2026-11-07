cmake_minimum_required(VERSION 3.24)
project(kvm_sandbox VERSION 0.1 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTORCC ON)
set(CMAKE_AUTOUIC ON)

find_package(Qt6 6.5 REQUIRED COMPONENTS Core Quick Qml QuickControls2)
find_package(PkgConfig REQUIRED)
pkg_check_modules(SODIUM REQUIRED IMPORTED_TARGET libsodium)

qt_standard_project_setup(REQUIRES 6.5)
qt_policy(SET QTP0004 NEW)

qt_add_executable(kvm-sandbox
    main.cpp
    authstore.cpp
    authstore.h
    backend.cpp
    backend.h
)

qt_add_qml_module(kvm-sandbox
    URI KvmSandbox
    VERSION 1.0
    QML_FILES qml/Main.qml
)

target_compile_definitions(kvm-sandbox PRIVATE
    SANDBOX_PROJECT_DIR="${CMAKE_CURRENT_SOURCE_DIR}/.."
)

target_link_libraries(kvm-sandbox PRIVATE
    Qt6::Core
    Qt6::Quick
    Qt6::Qml
    Qt6::QuickControls2
    PkgConfig::SODIUM
)

include(CTest)
if(BUILD_TESTING)
    add_executable(auth-smoke tests/auth_smoke.cpp authstore.cpp authstore.h)
    target_link_libraries(auth-smoke PRIVATE Qt6::Core PkgConfig::SODIUM)
    add_test(NAME auth-smoke COMMAND auth-smoke)
endif()
