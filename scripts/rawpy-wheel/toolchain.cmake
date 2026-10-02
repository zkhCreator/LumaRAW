# Purpose: constrain all private codec/LibRaw CMake package discovery to the
# declared arm64 prefix plus the selected Apple SDK.
# Inputs: DEPS_PREFIX, MACOS_SDK, CC, CXX, AR, RANLIB, STRIP, and MAKE are set
# by build_rawpy_wheel.py; outputs are arm64 macOS 14.0 native artifacts.
# Non-goals: this file does not change project build configuration or system
# package state. It deliberately keeps CMake's built-in system modules usable.

# Keep CMake in a native macOS configure (do not set CMAKE_SYSTEM_NAME, which
# marks even an arm64-on-arm64 build as cross-compiling in some projects).
set(CMAKE_SYSTEM_PROCESSOR arm64)
set(CMAKE_C_COMPILER "$ENV{CC}" CACHE FILEPATH "Pinned Apple C compiler" FORCE)
set(CMAKE_CXX_COMPILER "$ENV{CXX}" CACHE FILEPATH "Pinned Apple C++ compiler" FORCE)
set(CMAKE_AR "$ENV{AR}" CACHE FILEPATH "Pinned Apple archiver" FORCE)
set(CMAKE_RANLIB "$ENV{RANLIB}" CACHE FILEPATH "Pinned Apple ranlib" FORCE)
set(CMAKE_STRIP "$ENV{STRIP}" CACHE FILEPATH "Pinned Apple strip" FORCE)
set(CMAKE_MAKE_PROGRAM "$ENV{MAKE}" CACHE FILEPATH "Pinned make" FORCE)

set(CMAKE_OSX_ARCHITECTURES arm64 CACHE STRING "Private wheel architecture" FORCE)
set(CMAKE_OSX_DEPLOYMENT_TARGET 14.0 CACHE STRING "Private wheel minimum macOS" FORCE)
set(CMAKE_OSX_SYSROOT "$ENV{MACOS_SDK}" CACHE PATH "Selected Xcode SDK" FORCE)

set(CMAKE_FIND_ROOT_PATH "$ENV{DEPS_PREFIX};$ENV{MACOS_SDK}"
    CACHE STRING "Only declared codec prefix and Apple SDK" FORCE)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

set(CMAKE_FIND_USE_PACKAGE_ROOT_PATH FALSE)
set(CMAKE_FIND_USE_CMAKE_PATH FALSE)
set(CMAKE_FIND_USE_CMAKE_ENVIRONMENT_PATH FALSE)
set(CMAKE_FIND_USE_SYSTEM_ENVIRONMENT_PATH FALSE)
set(CMAKE_FIND_USE_INSTALL_PREFIX FALSE)
set(CMAKE_FIND_USE_PACKAGE_REGISTRY FALSE)
set(CMAKE_FIND_USE_SYSTEM_PACKAGE_REGISTRY FALSE)
set(CMAKE_FIND_USE_CMAKE_SYSTEM_PATH TRUE)
set(CMAKE_FIND_PACKAGE_NO_PACKAGE_REGISTRY TRUE)
set(CMAKE_FIND_PACKAGE_NO_SYSTEM_PACKAGE_REGISTRY TRUE)
# LibRaw's FindLCMS2 module calls pkg_check_modules unconditionally after
# find_package(PkgConfig). Keep that CMake helper definition available, but pin
# its executable to Apple's inert false command so it cannot inspect PATH.
set(PKG_CONFIG_EXECUTABLE "/usr/bin/false" CACHE FILEPATH "Disable pkg-config probing" FORCE)

set(CMAKE_MACOSX_RPATH TRUE)
set(CMAKE_INSTALL_NAME_DIR "@rpath" CACHE STRING "Relocatable dylib IDs" FORCE)
set(CMAKE_INSTALL_RPATH "@loader_path" CACHE STRING "Sibling dylib lookup" FORCE)
set(BASH_PROGRAM "/bin/bash" CACHE FILEPATH "Pinned Apple system bash" FORCE)

set(LCMS2_INCLUDE_DIR "$ENV{DEPS_PREFIX}/include" CACHE PATH "Pinned LCMS2 headers" FORCE)
set(LCMS2_LIBRARIES "$ENV{DEPS_PREFIX}/lib/liblcms2.dylib" CACHE FILEPATH "Pinned LCMS2 dylib" FORCE)

set(JPEG_INCLUDE_DIR "$ENV{DEPS_PREFIX}/include" CACHE PATH "Pinned JPEG headers" FORCE)
set(JPEG_INCLUDE_DIRS "$ENV{DEPS_PREFIX}/include" CACHE PATH "Pinned JPEG headers" FORCE)
set(JPEG_LIBRARY "$ENV{DEPS_PREFIX}/lib/libjpeg.dylib" CACHE FILEPATH "Pinned JPEG dylib" FORCE)
set(JPEG_LIBRARY_RELEASE "$ENV{DEPS_PREFIX}/lib/libjpeg.dylib" CACHE FILEPATH "Pinned JPEG dylib" FORCE)
set(JPEG_LIBRARY_DEBUG "$ENV{DEPS_PREFIX}/lib/libjpeg.dylib" CACHE FILEPATH "Pinned JPEG dylib" FORCE)

set(JASPER_INCLUDE_DIR "$ENV{DEPS_PREFIX}/include" CACHE PATH "Pinned JasPer headers" FORCE)
set(JASPER_INCLUDE_DIRS "$ENV{DEPS_PREFIX}/include" CACHE PATH "Pinned JasPer headers" FORCE)
set(JASPER_LIBRARIES "$ENV{DEPS_PREFIX}/lib/libjasper.dylib" CACHE FILEPATH "Pinned JasPer dylib" FORCE)
set(JASPER_LIBRARY "$ENV{DEPS_PREFIX}/lib/libjasper.dylib" CACHE FILEPATH "Pinned JasPer dylib" FORCE)
set(JASPER_LIBRARY_RELEASE "$ENV{DEPS_PREFIX}/lib/libjasper.dylib" CACHE FILEPATH "Pinned JasPer dylib" FORCE)
set(JASPER_LIBRARY_DEBUG "$ENV{DEPS_PREFIX}/lib/libjasper.dylib" CACHE FILEPATH "Pinned JasPer dylib" FORCE)

set(ZLIB_INCLUDE_DIR "$ENV{MACOS_SDK}/usr/include" CACHE PATH "Apple SDK zlib headers" FORCE)
set(ZLIB_LIBRARY "$ENV{MACOS_SDK}/usr/lib/libz.tbd" CACHE FILEPATH "Apple SDK zlib stub" FORCE)
set(ZLIB_LIBRARY_RELEASE "$ENV{MACOS_SDK}/usr/lib/libz.tbd" CACHE FILEPATH "Apple SDK zlib stub" FORCE)
set(ZLIB_LIBRARY_DEBUG "$ENV{MACOS_SDK}/usr/lib/libz.tbd" CACHE FILEPATH "Apple SDK zlib stub" FORCE)
set(MATH_LIBRARY "$ENV{MACOS_SDK}/usr/lib/libm.tbd" CACHE FILEPATH "Apple SDK math stub" FORCE)
