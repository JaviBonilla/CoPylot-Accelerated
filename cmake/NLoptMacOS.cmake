function(nlopt_macos_environment output directory)
  execute_process(COMMAND xcode-select -p
    OUTPUT_VARIABLE developer_dir ERROR_VARIABLE developer_error
    OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
  set(sdk "${CMAKE_OSX_SYSROOT}")
  set(sdk_status 0)
  if(NOT IS_ABSOLUTE "${sdk}")
    if(NOT sdk)
      set(sdk macosx)
    endif()
    execute_process(COMMAND xcrun --sdk "${sdk}" --show-sdk-path
      RESULT_VARIABLE sdk_status OUTPUT_VARIABLE sdk_path ERROR_VARIABLE sdk_error
      OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_STRIP_TRAILING_WHITESPACE)
  else()
    set(sdk_path "${sdk}")
  endif()
  if(NOT sdk_status STREQUAL "0" OR NOT IS_ABSOLUTE "${sdk_path}"
      OR NOT IS_DIRECTORY "${sdk_path}" OR sdk_path STREQUAL "/")
    message(FATAL_ERROR "NLopt macOS toolchain preflight could not resolve SDK '${sdk}' "
      "(${sdk_status}): ${sdk_path}\n${sdk_error}\n"
      "xcode-select -p: ${developer_dir}${developer_error}")
  endif()

  set(target_flags)
  foreach(arch IN LISTS CMAKE_OSX_ARCHITECTURES)
    list(APPEND target_flags -arch "${arch}")
  endforeach()
  if(CMAKE_OSX_DEPLOYMENT_TARGET)
    list(APPEND target_flags "-mmacosx-version-min=${CMAKE_OSX_DEPLOYMENT_TARGET}")
  endif()
  # AppleClang uses SDKROOT as its default -isysroot for compilation and linking.
  # An environment value also preserves SDK paths containing spaces, since this
  # Autoconf script expands CPPFLAGS as shell words in all three kinds of probes.
  string(JOIN " " cppflags "$ENV{CPPFLAGS}" ${target_flags})
  set(probe "${directory}/macos-link-test")
  file(WRITE "${probe}.c" "int main(void) { return 0; }\n")
  execute_process(COMMAND "${CMAKE_COMMAND}" -E env "SDKROOT=${sdk_path}"
    "${CMAKE_C_COMPILER}" ${target_flags} "${probe}.c" -o "${probe}"
    RESULT_VARIABLE link_status OUTPUT_QUIET ERROR_VARIABLE link_error)
  file(REMOVE "${probe}.c" "${probe}")
  if(NOT link_status STREQUAL "0")
    message(FATAL_ERROR "NLopt macOS toolchain preflight could not link (${link_status})\n"
      "Compiler: ${CMAKE_C_COMPILER}\nSDKROOT: ${sdk_path}\n"
      "Target flags: ${target_flags}\nxcode-select -p: ${developer_dir}${developer_error}\n"
      "${link_error}")
  endif()
  set("${output}" "SDKROOT=${sdk_path}" "CPPFLAGS=${cppflags}" PARENT_SCOPE)
endfunction()
