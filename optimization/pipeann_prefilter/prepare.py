#!/usr/bin/env python3
"""Build an isolated, pinned PipeANN checkout with a reversible route override."""
import argparse
import subprocess
from pathlib import Path

COMMIT = "2ec84fe20c37dc3cc236b66f7eba31c0cc80bf1e"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-root", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    root = args.course_root.resolve()
    destination = root / "systems/PipeANN_prefilter_verified"
    source = (args.source or root / "systems/PipeANN").resolve()
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite existing checkout: {destination}")
    subprocess.run(["git", "clone", "--shared", str(source), str(destination)], check=True)
    subprocess.run(["git", "-C", str(destination), "checkout", "--detach", COMMIT], check=True)
    path = destination / "src/search/spec_filter_search.cpp"
    content = path.read_text()
    content = content.replace("#include <limits>", "#include <limits>\n#include <cstdlib>\n#include <cerrno>\n#include <stdexcept>", 1)
    anchor = "    if (stats != nullptr) {\n      stats->n_filter[min_filter_type]++;"
    replacement = """    // Calibrate the route on this machine without changing either search path.
    // Zero/unset retains the original cost model. This threshold is opt-in.
    static const double prefilter_max_selectivity = []() {
      const char *value = std::getenv("FVS_PREFILTER_MAX_SELECTIVITY");
      if (value == nullptr) return 0.0;
      char *end = nullptr;
      errno = 0;
      const double threshold = std::strtod(value, &end);
      if (errno != 0 || end == value || *end != '\\0' ||
          !std::isfinite(threshold) || threshold < 0.0 || threshold > 1.0) {
        throw std::invalid_argument("FVS_PREFILTER_MAX_SELECTIVITY must be in [0,1]");
      }
      return threshold;
    }();
    if (prefilter_max_selectivity > 0.0 && selectivity <= prefilter_max_selectivity) {
      min_filter_type = PRE_FILTER;
    }

    if (stats != nullptr) {
      stats->n_filter[min_filter_type]++;"""
    if content.count(anchor) != 1:
        raise SystemExit("Pinned source does not contain the unique route-selection anchor")
    path.write_text(content.replace(anchor, replacement, 1))
    patch = Path(__file__).resolve().parent / "prefilter_route.patch"
    patch.write_bytes(subprocess.check_output(["git", "-C", str(destination), "diff", "--", str(path)]))
    subprocess.run(["cmake", "-S", str(destination), "-B", str(destination / "build"),
                    "-DCMAKE_BUILD_TYPE=Release", "-DIO_ENGINE=aio", "-DUSE_TCMALLOC=ON"], check=True)
    subprocess.run(["cmake", "--build", str(destination / "build"), "--target",
                    "search_disk_index_filtered", "-j", str(args.jobs)], check=True)
    print(destination, flush=True)


if __name__ == "__main__":
    main()
