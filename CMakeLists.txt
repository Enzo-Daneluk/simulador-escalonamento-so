cmake_minimum_required(VERSION 3.20)
project(SimuladorRT LANGUAGES NONE)

find_package(Python3 3.10 REQUIRED COMPONENTS Interpreter)

add_custom_target(simulador ALL
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_SOURCE_DIR}/construir.py"
        --destino "${CMAKE_SOURCE_DIR}/dist"
        --temporarios "${CMAKE_BINARY_DIR}/empacotamento"
    WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}"
    COMMENT "Testando os fontes e construindo o simulador autonomo"
    VERBATIM USES_TERMINAL)

# Permite rodar os testes do núcleo pelo comando ctest.
enable_testing()
add_test(NAME nucleo COMMAND "${Python3_EXECUTABLE}" -B -m unittest testes testes_regressao -v)
set_tests_properties(nucleo PROPERTIES WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
