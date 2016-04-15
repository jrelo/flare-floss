import os
import yaml
import pytest

import viv_utils

import footer
import floss.main as floss_main
import floss.identification_manager as im
import floss.stackstrings as stackstrings


def extract_strings(sample_path):
    """
    Deobfuscate strings from sample_path
    """
    vw = viv_utils.getWorkspace(sample_path)
    function_index = viv_utils.InstructionFunctionIndex(vw)
    decoding_functions_candidates = identify_decoding_functions(vw)
    decoded_strings = floss_main.decode_strings(vw, function_index, decoding_functions_candidates)
    decoded_stackstrings = stackstrings.extract_stackstrings(vw)
    decoded_strings.extend(decoded_stackstrings)
    return [ds.s for ds in decoded_strings]


def identify_decoding_functions(vw):
    selected_functions = floss_main.select_functions(vw, None)
    selected_plugin_names = floss_main.select_plugins(None)
    selected_plugins = filter(lambda p: str(p) in selected_plugin_names, floss_main.get_all_plugins())
    decoding_functions_candidates = im.identify_decoding_functions(vw, selected_plugins, selected_functions)
    return decoding_functions_candidates


def pytest_collect_file(parent, path):
    if path.basename == "test.yml":
        return YamlFile(path, parent)


class YamlFile(pytest.File):
    def collect(self):
        spec = yaml.safe_load(self.fspath.open())
        test_dir = os.path.dirname(str(self.fspath))
        for platform, archs in spec["Output Files"].items():
            for arch, filename in archs.items():
                filepath = os.path.join(test_dir, filename)
                if os.path.exists(filepath):
                    #and footer.has_footer(filepath):
                    yield FLOSSTest(self, platform, arch, filename, spec)


class FLOSSStringsNotExtracted(Exception):
    def __init__(self, expected, got):
        self.expected = expected
        self.got = got


class FLOSSTest(pytest.Item):
    def __init__(self, path, platform, arch, filename, spec):
        name = "{name:s}::{platform:s}::{arch:s}".format(
                name=spec["Test Name"],
                platform=platform,
                arch=arch)
        super(FLOSSTest, self).__init__(name, path)
        self.spec = spec
        self.platform = platform
        self.arch = arch
        self.filename = filename

    def runtest(self):
        xfail = self.spec.get("Xfail", {})
        if "all" in xfail:
            pytest.xfail("unsupported test case (known issue)")

        if "{0.platform:s}-{0.arch:s}".format(self) in xfail:
            pytest.xfail("unsupported platform&arch test case (known issue)")

        spec_path = self.location[0]
        test_dir = os.path.dirname(spec_path)
        test_path = os.path.join(test_dir, self.filename)

        if footer.has_footer(test_path):
            expected_strings = set(footer.read_footer(test_path)["all"])
        else:
            expected_strings = set(self.spec["Decoded strings"])

        found_strings = set(extract_strings(test_path))

        if expected_strings:
            if not (expected_strings <= found_strings):
                raise FLOSSStringsNotExtracted(expected_strings, found_strings)

    def reportinfo(self):
        return self.fspath, 0, "usecase: %s" % self.name

    def repr_failure(self, excinfo):
        if isinstance(excinfo.value, FLOSSStringsNotExtracted):
            expected = excinfo.value.expected
            got = excinfo.value.got
            return "\n".join([
                "FLOSS extraction failed:",
                "   expected: %s" % str(expected),
                "   got: %s" % str(got),
            ])

