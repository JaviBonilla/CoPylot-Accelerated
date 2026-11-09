# Explicit opt-in for local verification. No release or source archive target.
if(CMAKE_CROSSCOMPILING OR NOT CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|AMD64|amd64)$")
  message(FATAL_ERROR "Use a native x86-64 build to create a local package")
endif()
if(NOT CMAKE_CONFIGURATION_TYPES AND NOT CMAKE_BUILD_TYPE STREQUAL "Release")
  message(FATAL_ERROR "Configure a Release build for local packaging")
endif()

set(package_arch x86_64)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
  set(package_os linux)
  set(package_suffix .so)
elseif(WIN32 AND MSVC)
  set(package_os windows)
  set(package_suffix .dll)
elseif(APPLE AND (NOT CMAKE_OSX_ARCHITECTURES OR CMAKE_OSX_ARCHITECTURES STREQUAL "x86_64"))
  set(package_os macos)
  # SSC's pinned post-build copy expects .so on non-MSVC builds. Keep that
  # suffix for the Intel Mach-O library in the opt-in configuration only.
  set(package_suffix .so)
else()
  message(FATAL_ERROR "No local package recipe for this OS/compiler/architecture")
endif()

set_target_properties(solarpilot PROPERTIES
  OUTPUT_NAME hermite_optics SUFFIX "${package_suffix}" SKIP_BUILD_RPATH TRUE)
set(package_library "hermite_optics${package_suffix}")
set(package_variant cpu)
if(COPILOT_PORTABLE_LINUX_CPU)
  set(package_variant cpu-glibc2.34)
endif()
set(package_cuda_version "")
set(package_cuda_arch "")
if(SOLARPILOT_ENABLE_CUDA)
  set_target_properties(solarpilot PROPERTIES CUDA_RUNTIME_LIBRARY Shared)
  set(package_cuda_version "${CUDAToolkit_VERSION}")
  set(package_cuda_arch "${CMAKE_CUDA_ARCHITECTURES}")
  set(package_variant "cuda${CUDAToolkit_VERSION_MAJOR}.${CUDAToolkit_VERSION_MINOR}-sm${package_cuda_arch}")
  foreach(directory IN ITEMS "${CMAKE_SOURCE_DIR}" "${CMAKE_BINARY_DIR}")
    if(MSVC)
      target_compile_options(solarpilot PRIVATE "$<$<COMPILE_LANGUAGE:CUDA>:-Xcompiler=/pathmap:${directory}=.>")
    else()
      target_compile_options(solarpilot PRIVATE "$<$<COMPILE_LANGUAGE:CUDA>:-Xcompiler=-ffile-prefix-map=${directory}=.>")
    endif()
  endforeach()
endif()

find_package(Git REQUIRED)
function(package_git directory output)
  execute_process(
    COMMAND "${GIT_EXECUTABLE}" -C "${directory}" ${ARGN}
    COMMAND_ERROR_IS_FATAL ANY
    OUTPUT_VARIABLE result OUTPUT_STRIP_TRAILING_WHITESPACE)
  set("${output}" "${result}" PARENT_SCOPE)
endfunction()

package_git("${CMAKE_SOURCE_DIR}" package_revision rev-parse HEAD)
package_git("${CMAKE_SOURCE_DIR}" package_revision_short rev-parse --short=12 HEAD)
package_git("${CMAKE_SOURCE_DIR}" package_changes status --porcelain)
set(package_dirty false)
if(package_changes)
  set(package_dirty true)
  string(APPEND package_revision_short "-dirty")
endif()

file(READ "${CMAKE_SOURCE_DIR}/repos.lock.json" dependency_lock)
foreach(dependency IN ITEMS SolarPILOT ssc SolTrace)
  string(JSON expected GET "${dependency_lock}" "${dependency}" patched_sha)
  package_git("${CMAKE_SOURCE_DIR}/${dependency}" actual rev-parse HEAD)
  package_git("${CMAKE_SOURCE_DIR}/${dependency}" changes status --porcelain --untracked-files=no)
  if(NOT actual STREQUAL expected OR changes)
    message(FATAL_ERROR "${dependency} is not the clean pinned checkout. Run scripts/bootstrap.py.")
  endif()
  set("package_${dependency}_revision" "${actual}")
endforeach()

set(package_diagnostics false)
if(SOLARPILOT_ENABLE_FLUX_DIAGNOSTICS)
  set(package_diagnostics true)
endif()

set(package_generated "${CMAKE_CURRENT_BINARY_DIR}/local-package")
file(MAKE_DIRECTORY "${package_generated}")
configure_file(packaging/BUILD.json.in "${package_generated}/BUILD.json" @ONLY)
set(upstream_api "${CMAKE_SOURCE_DIR}/SolarPILOT/deploy/api")
file(READ "${upstream_api}/copylot.py" copylot_source)
# Drop obsolete commented-out developer paths. Preserve executable code and notices.
string(REGEX REPLACE "\n[ \t]*# self\\.pdll = CDLL\\([^\n]*" "" copylot_source "${copylot_source}")
file(WRITE "${package_generated}/copylot.py" "${copylot_source}")

install(CODE [[
  if(NOT CMAKE_INSTALL_CONFIG_NAME STREQUAL "Release")
    message(FATAL_ERROR "Use cpack -C Release for local packaging")
  endif()
]] COMPONENT local_runtime)
install(FILES "$<TARGET_FILE:solarpilot>" DESTINATION lib COMPONENT local_runtime)
install(FILES "${package_generated}/copylot.py" "${upstream_api}/pysoltrace.py"
  packaging/hermite_optics.py DESTINATION python COMPONENT local_runtime)
install(FILES packaging/example.py requirements.txt LICENSE THIRD_PARTY_NOTICES
  "${package_generated}/BUILD.json" DESTINATION . COMPONENT local_runtime)
install(FILES packaging/README.md DESTINATION . RENAME README.md COMPONENT local_runtime)
install(FILES docs/LICENSE DESTINATION licenses RENAME Project-documentation-CC-BY-4.0.txt
  COMPONENT local_runtime)
install(FILES
  licenses/SSC-LICENSE.txt licenses/SolarPILOT-LICENSE.md licenses/SolTrace-LICENSE.md
  licenses/NLopt-LICENSE.htm licenses/lp_solve-LICENSE.htm licenses/RapidXML-license.txt
  DESTINATION licenses COMPONENT local_runtime)

set(CPACK_PACKAGE_NAME "hermite-optics-local")
set(CPACK_PACKAGE_VERSION "0.0.0")
set(CPACK_PACKAGE_FILE_NAME "hermite-optics-local-${package_revision_short}-${package_os}-${package_arch}-${package_variant}")
set(CPACK_PACKAGE_DIRECTORY "${CMAKE_BINARY_DIR}/packages")
set(CPACK_INCLUDE_TOPLEVEL_DIRECTORY ON)
set(CPACK_VERBATIM_VARIABLES ON)
if(COPILOT_PORTABLE_LINUX_CPU)
  set(CPACK_PACKAGE_CHECKSUM SHA256)
endif()
# CPack selects source generators automatically when this list is empty.
# Disable them and remove the default whole-checkout input even if -G is supplied.
set(CPACK_SOURCE_GENERATOR "")
foreach(generator IN ITEMS 7Z CYGWIN RPM TBZ2 TGZ TXZ TZ ZIP)
  set(CPACK_SOURCE_${generator} OFF)
endforeach()
set(CPACK_SOURCE_INSTALLED_DIRECTORIES "")
set(CPACK_SOURCE_INSTALL_CMAKE_PROJECTS "")
set(CPACK_INSTALL_CMAKE_PROJECTS "${CMAKE_BINARY_DIR};${CMAKE_PROJECT_NAME};local_runtime;/")
if(WIN32)
  set(CPACK_GENERATOR ZIP)
else()
  set(CPACK_GENERATOR TGZ)
endif()
include(CPack)
file(APPEND "${CPACK_SOURCE_OUTPUT_CONFIG_FILE}"
  "\nmessage(FATAL_ERROR \"Source archives are disabled for local binary packaging\")\n")
