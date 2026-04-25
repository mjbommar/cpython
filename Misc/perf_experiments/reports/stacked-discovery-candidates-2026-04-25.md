# Profile Candidate Report

- Input: `/tmp/stacked-discovery-2026-04-24-refresh-inproc.txt`
- Total samples: `25839`
- Top rows: `30`

## Top Groups By Leaf Samples

| Rank | Group | Samples | Share |
| --- | --- | --- | --- |
| 1 | Lib/selectors.py | 8761 | 33.91% |
| 2 | Lib/test | 4943 | 19.13% |
| 3 | unresolved | 3665 | 14.18% |
| 4 | Python/gc.c | 2965 | 11.47% |
| 5 | Lib/subprocess.py | 962 | 3.72% |
| 6 | Lib/pickle.py | 897 | 3.47% |
| 7 | Lib/shutil.py | 701 | 2.71% |
| 8 | Lib/tarfile.py | 503 | 1.95% |
| 9 | Lib/dbm | 488 | 1.89% |
| 10 | Lib/compression | 322 | 1.25% |
| 11 | Lib/unittest | 227 | 0.88% |
| 12 | Lib/bz2.py | 175 | 0.68% |
| 13 | Lib/os.py | 157 | 0.61% |
| 14 | Lib/tokenize.py | 138 | 0.53% |
| 15 | Lib/dataclasses.py | 135 | 0.52% |
| 16 | Lib/random.py | 104 | 0.40% |
| 17 | Lib/lzma.py | 97 | 0.38% |
| 18 | Lib/ast.py | 80 | 0.31% |
| 19 | Lib/dis.py | 61 | 0.24% |
| 20 | Lib/posixpath.py | 56 | 0.22% |
| 21 | Lib/importlib | 55 | 0.21% |
| 22 | Lib/pathlib | 53 | 0.21% |
| 23 | Lib/contextlib.py | 49 | 0.19% |
| 24 | Lib/multiprocessing | 41 | 0.16% |
| 25 | Lib/pickletools.py | 40 | 0.15% |
| 26 | Lib/re | 33 | 0.13% |
| 27 | Lib/traceback.py | 31 | 0.12% |
| 28 | Lib/argparse.py | 21 | 0.08% |
| 29 | Lib/threading.py | 20 | 0.08% |
| 30 | Lib/gzip.py | 16 | 0.06% |

## Top Cumulative Frames

| Rank | Frame | Samples | Share | Resolved |
| --- | --- | --- | --- | --- |
| 1 | `<frozen runpy>:_run_code:85` | 51677 | 200.00% | Lib/runpy.py:65 |
| 2 | `suite.py:BaseTestSuite.__call__:84` | 51123 | 197.85% | Lib/unittest/suite.py:84 |
| 3 | `suite.py:TestSuite.run:122` | 50843 | 196.77% | Lib/unittest/suite.py:122 |
| 4 | `tid:1783194` | 25839 | 100.00% | (unresolved) |
| 5 | `<frozen runpy>:_run_module_as_main:194` | 25839 | 100.00% | Lib/runpy.py:172 |
| 6 | `<frozen runpy>:run_module:222` | 25838 | 100.00% | Lib/runpy.py:199 |
| 7 | `<frozen runpy>:_run_module_code:95` | 25838 | 100.00% | Lib/runpy.py:90 |
| 8 | `__main__.py:<module>:2` | 25814 | 99.90% | (unresolved) |
| 9 | `main.py:main:796` | 25813 | 99.90% | ./Tools/check-c-api-docs/main.py:796 |
| 10 | `main.py:Regrtest.main:788` | 25812 | 99.90% | ./Tools/check-c-api-docs/main.py:788 |
| 11 | `main.py:Regrtest.run_tests:595` | 25811 | 99.89% | Lib/test/libregrtest/main.py:595 |
| 12 | `main.py:Regrtest._run_tests:560` | 25811 | 99.89% | Lib/test/libregrtest/main.py:560 |
| 13 | `main.py:Regrtest.run_tests_sequentially:420` | 25810 | 99.89% | Lib/test/libregrtest/main.py:420 |
| 14 | `main.py:Regrtest.run_test:390` | 25810 | 99.89% | Lib/test/libregrtest/main.py:390 |
| 15 | `single.py:run_single_test:348` | 25810 | 99.89% | Lib/test/libregrtest/single.py:348 |
| 16 | `single.py:_runtest:319` | 25806 | 99.87% | Lib/test/libregrtest/single.py:319 |
| 17 | `single.py:_runtest_env_changed_exc:210` | 25114 | 97.19% | Lib/test/libregrtest/single.py:210 |
| 18 | `single.py:_load_run_test:165` | 24631 | 95.32% | Lib/test/libregrtest/single.py:165 |
| 19 | `single.py:regrtest_runner:118` | 24631 | 95.32% | Lib/test/libregrtest/single.py:118 |
| 20 | `single.py:_load_run_test.<locals>.test_func:162` | 24631 | 95.32% | Lib/test/libregrtest/single.py:162 |
| 21 | `single.py:run_unittest:42` | 24575 | 95.11% | Lib/test/libregrtest/single.py:42 |
| 22 | `single.py:_run_suite:84` | 24575 | 95.11% | Lib/test/libregrtest/single.py:84 |
| 23 | `testresult.py:QuietRegressionTestRunner.run:148` | 24575 | 95.11% | Lib/test/libregrtest/testresult.py:148 |
| 24 | `case.py:TestCase.__call__:723` | 24272 | 93.94% | Lib/unittest/case.py:723 |
| 25 | `case.py:TestCase.run:667` | 22844 | 88.41% | Lib/unittest/case.py:667 |
| 26 | `case.py:TestCase._callTestMethod:613` | 22833 | 88.37% | Lib/unittest/case.py:613 |
| 27 | `subprocess.py:Popen.communicate:1286` | 8770 | 33.94% | Lib/subprocess.py:1286 |
| 28 | `selectors.py:_PollLikeSelector.select:398` | 8761 | 33.91% | Lib/selectors.py:398 |
| 29 | `subprocess.py:Popen._communicate:2317` | 8715 | 33.73% | Lib/subprocess.py:2317 |
| 30 | `script_helper.py:_assert_python:165` | 8705 | 33.69% | Lib/test/support/script_helper.py:165 |

## Top Leaf Frames

| Rank | Frame | Samples | Share | Resolved |
| --- | --- | --- | --- | --- |
| 1 | `selectors.py:_PollLikeSelector.select:398` | 8761 | 33.91% | Lib/selectors.py:398 |
| 2 | `<GC>` | 2965 | 11.47% | Python/gc.c |
| 3 | `test_compile.py:TestSpecifics.test_compiler_recursion_limit.<locals>.check_limit:741` | 2479 | 9.59% | Lib/test/test_compile.py:741 |
| 4 | `test_random.py:MersenneTwister_TestBasicOps.test_getrandbits_2G_bits:832` | 799 | 3.09% | Lib/test/test_random.py:832 |
| 5 | `subprocess.py:Popen.communicate:1273` | 785 | 3.04% | Lib/subprocess.py:1273 |
| 6 | `test_compile.py:TestSpecifics.test_big_dict_literal:1392` | 368 | 1.42% | Lib/test/test_compile.py:1392 |
| 7 | `_streams.py:DecompressReader.read:103` | 320 | 1.24% | Lib/compression/_common/_streams.py:103 |
| 8 | `sqlite3.py:_Database._execute:84` | 257 | 0.99% | Lib/dbm/sqlite3.py:84 |
| 9 | `shutil.py:_rmtree_safe_fd_step:753` | 211 | 0.82% | Lib/shutil.py:753 |
| 10 | `pickle.py:_Unpickler.load:1580` | 201 | 0.78% | Lib/pickle.py:1580 |
| 11 | `glob.py:_StringGlobber._scandir_entries:548` | 194 | 0.75% | (unresolved) |
| 12 | `glob.py:_StringGlobber._scandir_entries:547` | 189 | 0.73% | (unresolved) |
| 13 | `sqlite3.py:_Database.__init__:75` | 151 | 0.58% | Lib/dbm/sqlite3.py:75 |
| 14 | `dataclasses.py:_FuncBuilder.add_fns_to_class:505` | 135 | 0.52% | Lib/dataclasses.py:505 |
| 15 | `<frozen os>:makedirs:247` | 129 | 0.50% | Lib/os.py:222 |
| 16 | `pickle.py:_Pickler.save:651` | 125 | 0.48% | Lib/pickle.py:651 |
| 17 | `shutil.py:_rmtree_safe_fd_step:778` | 120 | 0.46% | Lib/shutil.py:778 |
| 18 | `subprocess.py:Popen._try_wait:2119` | 111 | 0.43% | Lib/subprocess.py:2119 |
| 19 | `bz2.py:BZ2File.close:109` | 108 | 0.42% | Lib/bz2.py:109 |
| 20 | `tarfile.py:_Stream._read:556` | 102 | 0.39% | Lib/tarfile.py:556 |
| 21 | `test_random.py:TestBasicOps.test_autoseed:40` | 100 | 0.39% | Lib/test/test_random.py:40 |
| 22 | `pickletester.py:AbstractPicklerUnpicklerObjectTests._check_multiple_unpicklings:5189` | 95 | 0.37% | Lib/test/pickletester.py:5189 |
| 23 | `test_pickle.py:PyPicklerTests.loads:98` | 89 | 0.34% | Lib/test/test_pickle.py:98 |
| 24 | `shutil.py:_rmtree_safe_fd_step:791` | 88 | 0.34% | Lib/shutil.py:791 |
| 25 | `sqlite3.py:_Database.close:118` | 80 | 0.31% | Lib/dbm/sqlite3.py:118 |
| 26 | `os_helper.py:unlink:373` | 78 | 0.30% | Lib/test/support/os_helper.py:373 |
| 27 | `pickle.py:_Unpickler.load:1576` | 77 | 0.30% | Lib/pickle.py:1576 |
| 28 | `shutil.py:_rmtree_safe_fd_step:777` | 76 | 0.29% | Lib/shutil.py:777 |
| 29 | `pickletester.py:AbstractUnpickleTests.assert_is_copy:749` | 75 | 0.29% | Lib/test/pickletester.py:749 |
| 30 | `<frozen os>:_spawnvef:932` | 72 | 0.28% | (unresolved) |

## How To Use This Report

- Start new work at the highest-signal group that is still unresolved or under-reviewed.
- Split by experiment family before touching code.
- Resolve unresolved symbols manually if they remain interesting after the first pass.
- Use leaf-heavy frames to find wrapper overhead; use cumulative-heavy frames to find subsystem winners.
