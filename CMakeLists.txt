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
if(BUILD_COPILOT_API)
  target_link_libraries(solarpilot Threads::Threads)
  if(UNIX AND NOT APPLE)
    target_link_options(solarpilot PRIVATE -Wl,--no-undefined)
  endif()
  set_target_properties(solarpilot PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/lib")
endif()
