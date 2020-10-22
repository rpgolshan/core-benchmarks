# pylint: disable=redefined-outer-name
"""Uses PMUs to verify branch behavior"""
import os
import pytest
import platform
import re
from frontend.code_generator.user_callgraph import Callgraph
from frontend.code_generator.source_generator import SourceGenerator
import sh


@pytest.fixture
def rootdir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        os.path.pardir)


@pytest.fixture
def resources(rootdir):
    return os.path.join(rootdir, 'resources')


@pytest.mark.parametrize('depth', [10, 11, 12, 13, 14, 15])
def test_dfs(resources, tmpdir, depth):
    test_file = os.path.join(resources, 'dfs', f'dfs_depth{depth}_cfg.pb')
    cfg = Callgraph.from_proto(test_file)
    source_gen = SourceGenerator(tmpdir, cfg)
    source_gen.write_files(num_files=24)
    compile_to_output(tmpdir)
    binary = os.path.join(tmpdir, source_gen.benchmark_name)
    iterations = 100000
    expected = iterations * depth
    assert run_perf_and_compare_output(binary,
                                       iterations=iterations,
                                       expected=expected,
                                       tolerance=1000)


def test_dfs_indirect(resources, tmpdir):
    test_file = os.path.join(resources, 'dfs', 'dfs_depth10_indirect.pb')
    cfg = Callgraph.from_proto(test_file)
    source_gen = SourceGenerator(tmpdir, cfg)
    source_gen.write_files(num_files=24)
    compile_to_output(tmpdir)
    binary = os.path.join(tmpdir, source_gen.benchmark_name)
    iterations = 100000
    expected = iterations * 10
    assert run_perf_and_compare_output(binary,
                                       iterations=iterations,
                                       expected=expected,
                                       tolerance=1000)


@pytest.mark.skip
@pytest.mark.parametrize('depth,callchains',
                         [(10, 100), (10, 500), (10, 1000), (10, 1500),
                          (10, 2000), (20, 100), (20, 500), (20, 1000),
                          (20, 1500), (20, 2000), (30, 100), (30, 500),
                          (30, 1000), (30, 1500), (30, 2000), (40, 100),
                          (40, 500), (40, 1000), (40, 1500), (40, 2000),
                          (50, 100), (50, 500), (50, 1000), (50, 1500),
                          (50, 2000)])
def test_ichase(resources, tmpdir, depth, callchains):
    test_file = os.path.join(resources, 'ichase',
                             f'ichase_depth{depth}_chains{callchains}_cfg.pb')
    cfg = Callgraph.from_proto(test_file)
    source_gen = SourceGenerator(tmpdir, cfg)
    source_gen.write_files()
    compile_to_output(tmpdir)
    binary = os.path.join(tmpdir, source_gen.benchmark_name)
    iterations = 100000000 // callchains
    expected = iterations * depth * callchains + iterations
    assert run_perf_and_compare_output(binary,
                                       iterations,
                                       expected=expected,
                                       tolerance=1000)


def get_perf_name_events():
    arch = platform.machine()
    if arch == 'x86_64':
        name = 'BR_INST_RETIRED.NEAR_CALL:u'
        #  name = 'cpu/event=0xc4,umask=0x2/u'
        #  events = [f'cpu/event=0xc4,umask=0x2/u', 'instructions:u',
        # 'cycles:u', 'FRONTEND_RETIRED.L1I_MISS:u']
        events = [
            'BR_INST_RETIRED.NEAR_CALL:u',
            'BR_INST_RETIRED.ALL_BRANCHES:u',
            'instructions:u',
            'cycles:u',
        ]
    elif arch == 'aarch64':
        name = 'r078:u'
        events = ['r078:u', 'r079:u', 'r07a:u', 'r08:u', 'r011:u', 'r028:u']
    return name, events


def run_perf_and_compare_output(binary, iterations, expected, tolerance):
    perf = sh.Command('perf')
    name, events = get_perf_name_events()
    output = str(
        perf('stat',
             *[f'-e {event}' for event in events],
             '-r',
             10,
             binary,
             '-l',
             iterations,
             _err_to_out=True))
    print(output)
    match = re.search(r'(\d+)\s*{}'.format(name), output)
    if not match:
        raise RuntimeError('Unexpected output from perf:\n{}'.format(output))
    number = int(match.group(1))
    csv = []
    for event in events:
        match = re.search(r'(\d+)\s*{}'.format(event), output)
        csv.append(match.group(1))
    print('results:', ' '.join(csv))
    return abs(number - expected) <= tolerance


def compile_to_output(directory):
    """ WARNING. THIS ASSUMES RUNNING ON x86 """
    make = sh.Command('make')
    arguments = ['-C', directory]
    count = os.cpu_count()
    if count:
        arguments.append(f'-j{count}')
    make(*arguments)
