cmake_minimum_required(VERSION 3.24)
project(copilot_headless LANGUAGES C CXX)
option(BUILD_COPILOT_API "Build the headless CoPylot shared library" ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
set(CMAKE_CXX_STANDARD 11)
find_package(Threads REQUIRED)
# The release's top-level CMake builds wxWidgets GUI. Include only coretrace.
add_subdirectory(SolTrace/coretrace EXCLUDE_FROM_ALL)
# SSC's solarpilot-develop superbuild contains only shared/core/nlopt/lpsolve.
set(ENV{CORETRACEDIR} "${CMAKE_CURRENT_SOURCE_DIR}/SolTrace/coretrace")
add_subdirectory(ssc EXCLUDE_FROM_ALL)
if(UNIX)
  # Bundled NLopt expects an Autoconf-generated header on Linux/macOS.
  set(nlopt_config_dir "${CMAKE_BINARY_DIR}/nlopt-config")
  file(MAKE_DIRECTORY "${nlopt_config_dir}")
  if(NOT EXISTS "${nlopt_config_dir}/config.h")
    execute_process(COMMAND "${CMAKE_COMMAND}" -E env
      "CC=${CMAKE_C_COMPILER}" "CXX=${CMAKE_CXX_COMPILER}"
      "${CMAKE_CURRENT_SOURCE_DIR}/ssc/nlopt/configure" --enable-shared=no
      WORKING_DIRECTORY "${nlopt_config_dir}"
      RESULT_VARIABLE nlopt_config_status
      OUTPUT_FILE "${nlopt_config_dir}/configure.log"
      ERROR_FILE "${nlopt_config_dir}/configure-error.log")
    if(NOT nlopt_config_status EQUAL 0)
      message(FATAL_ERROR "NLopt configure failed; see ${nlopt_config_dir}/configure*.log")
    endif()
  endif()
  target_include_directories(nlopt PRIVATE "${nlopt_config_dir}")
endif()
# CoPylot uses weather parsing and util only, not SSC's PV/battery/MPFIT code.
set_property(TARGET shared PROPERTY SOURCES
  "${CMAKE_CURRENT_SOURCE_DIR}/ssc/shared/lib_weatherfile.cpp"
  "${CMAKE_CURRENT_SOURCE_DIR}/ssc/shared/lib_util.cpp")
if(BUILD_COPILOT_API)
  target_link_libraries(solarpilot Threads::Threads)
  if(UNIX AND NOT APPLE)
    target_link_options(solarpilot PRIVATE -Wl,--no-undefined)
  endif()
  set_target_properties(solarpilot PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
endif()
