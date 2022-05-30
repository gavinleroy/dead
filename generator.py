#!/usr/bin/env python3

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
from abc import ABC, abstractmethod
from multiprocessing import Process, Queue
from os import listdir
from os.path import join as pjoin
from pathlib import Path
from random import randint
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import TYPE_CHECKING, Generator, Optional, Union, Callable

import builder
import checker
import parsers
import patchdatabase
import utils

if TYPE_CHECKING:
    from patchdatabase import PatchDB


def run_csmith(csmith: str) -> str:
    """Generate random code with csmith.

    Args:
        csmith (str): Path to executable or name in $PATH to csmith.

    Returns:
        str: csmith generated program.
    """
    tries = 0
    while True:
        options = [
            "arrays",
            "bitfields",
            "checksum",
            "comma-operators",
            "compound-assignment",
            "consts",
            "divs",
            "embedded-assigns",
            "jumps",
            "longlong",
            "force-non-uniform-arrays",
            "math64",
            "muls",
            "packed-struct",
            "paranoid",
            "pointers",
            "structs",
            "inline-function",
            "return-structs",
            "arg-structs",
            "dangling-global-pointers",
        ]

        cmd = [
            csmith,
            "--no-unions",
            "--safe-math",
            "--no-argc",
            "--no-volatiles",
            "--no-volatile-pointers",
        ]
        for option in options:
            if randint(0, 1):
                cmd.append(f"--{option}")
            else:
                cmd.append(f"--no-{option}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if result.returncode == 0:
            return result.stdout.decode("utf-8")
        else:
            tries += 1
            if tries > 10:
                raise Exception("CSmith failed 10 times in a row!")

def run_yarpgen(yarpgen: str) -> str:
    """Generate random code with YARPGen.

    Args:
        yarpgen (str): Path to executable or name in $PATH to yarpgen.

    Returns:
        str: YARPGen generated program concatenated together
             in the order (init.h ++ func.c ++ driver.c).
    """
    tries = 0
    while True:
        with TemporaryDirectory() as out_dir:
            nsa_options = [
                "inp-as-args",
                "emit-align-attr",
                "emit-pragmas",
                "allow-ub-in-dc"
            ]
            tf_options = [
                # "unique-align-size",
                "allow-dead-data",
                "param-shuffle",
                "expl-loop-param"
            ]
            align_sizes = [ "16", "32", "64" ]
            nsa = [ "none", "some", "all" ]
            nea = [ "none", "exprs", "all" ]
            tf = [ "true", "false" ]
            cmd = [
                yarpgen,
                "--std=c", # FIXME can we bump this to use either c|c++?
                f"--out-dir={out_dir}"
            ]
            for option in nsa_options:
                ri = randint(0, 2)
                cmd.append(f"--{option}={nsa[ri]}")
            for option in tf_options:
                ri = randint(0, 1)
                cmd.append(f"--{option}={tf[ri]}")
            # --mutate={none | exprs | all}
            ri = randint(0, 2)
            cmd.append(f"--mutate={nea[ri]}")
            ri = randint(0, 2)
            cmd.append(f"--align-size={align_sizes[ri]}")
            # gen_files = ['init.h', 'func.c', 'driver.c']
            gen_files = ['driver.c', 'func.c']
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            if result.returncode == 0:
                # NOTE YARPGen puts init.h, func.c, and driver.c into the directory
                # {out_dir}. These can be concatenated into a single file and returned.
                # content = list(map(lambda fn: Path(pjoin(out_dir, fn)).read_text(),
                #         gen_files))
                content = []
                for name in gen_files:
                    with open(pjoin(out_dir, name), 'r') as f:
                        content += [f.readlines()]
                # remove init.h include in func.c
                assert content[1][5] == '#include "init.h"\n'
                del content[1][5]
                concatenated = ''.join(sum(content, []))
                # NOTE FIXME this is a super hack
                # The DCEI tool makes all global variables and functions `static`,
                # however, it has a BUG and does not make forward declarations static.
                # This breaks valid C code and thus it's easier to just make the test function
                # static.
                concatenated = concatenated.replace('void test', 'static void test')
                return concatenated
            else:
                logging.debug(f"YARPGen failed with {result}")
                tries += 1
                if tries > 100:
                    raise Exception("YARPGen failed 10 times in a row!")


def instrument_program(dcei: Path, file: Path, include_paths: list[str]) -> str:
    """Instrument a given file i.e. put markers in the file.

    Args:
        dcei (Path): Path to dcei executable.
        file (Path): Path to code file to be instrumented.
        include_paths (list[str]):

    Returns:
        str: Marker prefix. Here: 'DCEMarker'
    """
    cmd = [str(dcei), str(file)]
    for path in include_paths:
        cmd.append(f"--extra-arg=-isystem{str(path)}")
    utils.run_cmd(cmd)
    return "DCEMarker"


def generate_file(
    gen_program: Callable[[], str],
    config: utils.NestedNamespace,
    exec_cfg: utils.NestedNamespace,
    additional_flags: str
) -> tuple[str, str]:
    """Generate an instrumented program.

    Args:
        config (utils.NestedNamespace): THE config
        additional_flags (str): Additional flags to use when
            compiling the program when checking.

    Returns:
        tuple[str, str]: Marker prefix and instrumented code.
    """
    additional_flags += f" -I {exec_cfg.include_path}"
    while True:
        try:
            logging.debug("Generating new candidate...")
            candidate = gen_program()
            if len(candidate) > exec_cfg.max_size:
                continue
            if len(candidate) < exec_cfg.min_size:
                continue
            with NamedTemporaryFile(suffix=".c") as ntf:
                with open(ntf.name, "w") as f:
                    print(candidate, file=f)
                logging.debug("Checking if program is sane...")
                # FIXME reenable
                # if not checker.sanitize(
                #     config.gcc.sane_version,
                #     config.llvm.sane_version,
                #     config.ccomp,
                #     Path(ntf.name),
                #     additional_flags,
                # ):
                #     continue
                include_paths = utils.find_include_paths(
                    config.llvm.sane_version, ntf.name, additional_flags
                )
                include_paths.append(exec_cfg.include_path)
                logging.debug("Instrumenting candidate...")
                marker_prefix = instrument_program(
                    config.dcei, Path(ntf.name), include_paths
                )
                with open(ntf.name, "r") as f:
                    return marker_prefix, f.read()

            return marker_prefix, candidate
        except subprocess.TimeoutExpired:
            pass


class CaseGenerator(ABC):
    def __init__(
        self,
        config: utils.NestedNamespace,
        patchdb: PatchDB,
        cores: Optional[int] = None,
    ):
        self.config: utils.NestedNamespace = config
        self.builder: builder.Builder = builder.Builder(config, patchdb, cores)
        self.chkr: checker.Checker = checker.Checker(config, self.builder)
        self.procs: list[Process] = []
        self.try_counter: int = 0

    @abstractmethod
    def _get_runner_details(
            self
    ) -> tuple[Callable[[], str], util.NestedNamespace, list[str]]:
        """Get Runner Details

        Returns:
            Callable[[str], str]: Function, given an executable will return a generated program.
            util.NestedNamespace: The configuration for the specific executable.
            list[str]: Additional flags that should be added to the scenario.
        """
        pass

    def generate_interesting_case(self, scenario: utils.Scenario) -> utils.Case:
        """Generate a case which is interesting i.e. has one compiler which does
        not eliminate a marker (from the target settings) a and at least one from
        the attacker settings.

        Args:
            scenario (utils.Scenario): Which compiler to compare.

        Returns:
            utils.Case: Intersting case.
        """
        (prog_generator, exec_config, additional_flags) = self._get_runner_details()
        scenario.add_flags(additional_flags)

        self.try_counter = 0
        while True:
            self.try_counter += 1
            logging.debug("Generating new candidate...")
            marker_prefix, candidate_code = generate_file(
                prog_generator, self.config, exec_config, ""
            )

            # Find alive markers
            logging.debug("Getting alive markers...")
            try:
                target_alive_marker_list = [
                    (
                        tt,
                        builder.find_alive_markers(
                            candidate_code, tt, marker_prefix, self.builder
                        ),
                    )
                    for tt in scenario.target_settings
                ]

                tester_alive_marker_list = [
                    (
                        tt,
                        builder.find_alive_markers(
                            candidate_code, tt, marker_prefix, self.builder
                        ),
                    )
                    for tt in scenario.attacker_settings
                ]
            except builder.CompileError:
                continue

            target_alive_markers = set()
            for _, marker_set in target_alive_marker_list:
                target_alive_markers.update(marker_set)

            # Extract reduce cases
            logging.debug("Extracting reduce cases...")
            for marker in target_alive_markers:
                good: list[utils.CompilerSetting] = []
                for good_setting, good_alive_markers in tester_alive_marker_list:
                    if (
                        marker not in good_alive_markers
                    ):  # i.e. the setting eliminated the call
                        good.append(good_setting)

                # Find bad cases
                if len(good) > 0:
                    good_opt_levels = [gs.opt_level for gs in good]
                    for bad_setting, bad_alive_markers in target_alive_marker_list:
                        # XXX: Here you can enable inter-opt_level comparison!
                        if (
                            marker in bad_alive_markers
                            and bad_setting.opt_level in good_opt_levels
                        ):  # i.e. the setting didn't eliminate the call
                            # Create reduce case
                            case = utils.Case(
                                code=candidate_code,
                                marker=marker,
                                bad_setting=bad_setting,
                                good_settings=good,
                                scenario=scenario,
                                reduced_code=None,
                                bisection=None,
                                path=None,
                            )
                            # TODO: Optimize interestingness test and document behaviour
                            try:
                                if self.chkr.is_interesting(case):
                                    logging.info(
                                        f"Try {self.try_counter}: Found case! LENGTH: {len(candidate_code)}"
                                    )
                                    return case
                            except builder.CompileError:
                                continue
            else:
                logging.debug(
                    f"Try {self.try_counter}: Found no case. Onto the next one!"
                )

    def _wrapper_interesting(self, queue: Queue[str], scenario: utils.Scenario) -> None:
        """Wrapper for generate_interesting_case for easier use
        with python multiprocessing.

        Args:
            queue (Queue): The multiprocessing queue to do IPC with.
            scenario (utils.Scenario): Scenario
        """
        logging.info("Starting worker...")
        while True:
            case = self.generate_interesting_case(scenario)
            queue.put(json.dumps(case.to_jsonable_dict()))

    def parallel_interesting_case_file(
        self,
        config: utils.NestedNamespace,
        scenario: utils.Scenario,
        processes: int,
        output_dir: os.PathLike[str],
        start_stop: Optional[bool] = False,
    ) -> Generator[Path, None, None]:
        """Generate interesting cases in parallel
        WARNING: If you use this method, you have to call `terminate_processes`

        Args:
            config (utils.NestedNamespace): THE config.
            scenario (utils.Scenario): Scenario.
            processes (int): Amount of jobs.
            output_dir (os.PathLike): Directory where to output the found cases.
            start_stop (Optional[bool]): Whether or not stop the processes when
                finding a case. This is useful when running a pipeline and thus
                the processing power is needed somewhere else.

        Returns:
            Generator[Path, None, None]: Interesting case generator giving paths.
        """
        gen = self.parallel_interesting_case(config, scenario, processes, start_stop)

        counter = 0
        while True:
            case = next(gen)
            h = hash(str(case))
            h = max(h, -h)
            path = Path(pjoin(output_dir, f"case_{counter:08}-{h:019}.tar"))
            logging.debug("Writing case to {path}...")
            case.to_file(path)
            yield path
            counter += 1

    def parallel_interesting_case(
        self,
        config: utils.NestedNamespace,
        scenario: utils.Scenario,
        processes: int,
        start_stop: Optional[bool] = False,
    ) -> Generator[utils.Case, None, None]:
        """Generate interesting cases in parallel
        WARNING: If you use this method, you have to call `terminate_processes`

        Args:
            config (utils.NestedNamespace): THE config.
            scenario (utils.Scenario): Scenario.
            processes (int): Amount of jobs.
            output_dir (os.PathLike): Directory where to output the found cases.
            start_stop (Optional[bool]): Whether or not stop the processes when
                finding a case. This is useful when running a pipeline and thus
                the processing power is needed somewhere else.

        Returns:
            Generator[utils.Case, None, None]: Interesting case generator giving Cases.
        """

        queue: Queue[str] = Queue()

        # Create processes
        self.procs = [
            Process(
                target=self._wrapper_interesting,
                args=(queue, scenario),
            )
            for _ in range(processes)
        ]

        # Start processes
        for p in self.procs:
            p.daemon = True
            p.start()

        # read queue
        while True:
            # TODO: handle process failure
            case_str: str = queue.get()

            case = utils.Case.from_jsonable_dict(config, json.loads(case_str))

            if start_stop:
                # Send processes to "sleep"
                logging.debug("Stopping workers...")
                for p in self.procs:
                    if p.pid is None:
                        continue
                    os.kill(p.pid, signal.SIGSTOP)
            yield case
            if start_stop:
                logging.debug("Restarting workers...")
                # Awake processes again for further search
                for p in self.procs:
                    if p.pid is None:
                        continue
                    os.kill(p.pid, signal.SIGCONT)

    def terminate_processes(self) -> None:
        for p in self.procs:
            if p.pid is None:
                continue
            # This is so cruel
            os.kill(p.pid, signal.SIGCONT)
            p.terminate()


class CSmithCaseGenerator(CaseGenerator):
    def _get_runner_details(
            self
    ) -> tuple[Callable[[], str], util.NestedNamespace, list[str]]:
        # Because the resulting code will be of csmith origin, we have to add
        # the csmith include path to all settings
        gen_prog = lambda: run_csmith(self.config.csmith.executable)
        exec_config = self.config.csmith
        additional_flags = [f"-I{self.config.csmith.include_path}"]
        return (gen_prog, exec_config, additional_flags)

class YARPGenCaseGenerator(CaseGenerator):
    def _get_runner_details(
            self
    ) -> tuple[Callable[[], str], util.NestedNamespace, list[str]]:
        gen_prog = lambda: run_yarpgen(self.config.yarpgen.executable)
        exec_config = self.config.yarpgen
        additional_flags = []
        return (gen_prog, exec_config, additional_flags)


if __name__ == "__main__":
    config, args = utils.get_config_and_parser(parsers.generator_parser())

    cores = args.cores

    patchdb = patchdatabase.PatchDB(config.patchdb)
    # case_generator: CaseGenerator = CSmithCaseGenerator(config, patchdb, cores)
    case_generator: CaseGenerator = YARPGenCaseGenerator(config, patchdb, cores)

    if args.interesting:
        scenario = utils.Scenario([], [])
        if args.scenario:
            scenario = utils.Scenario.from_file(config, Path(args.scenario))

        if not args.scenario and args.targets is None:
            print(
                "--targets is required for --interesting if you don't specify a scenario"
            )
            exit(1)
        elif args.targets:
            target_settings = utils.get_compiler_settings(
                config, args.targets, default_opt_levels=args.targets_default_opt_levels
            )
            scenario.target_settings = target_settings

        if not args.scenario and args.additional_compilers is None:
            print(
                "--additional-compilers is required for --interesting if you don't specify a scenario"
            )
            exit(1)
        elif args.additional_compilers:
            additional_compilers = utils.get_compiler_settings(
                config,
                args.additional_compilers,
                default_opt_levels=args.additional_compilers_default_opt_levels,
            )

            scenario.attacker_settings = additional_compilers

        if args.output_directory is None:
            print("Missing output directory!")
            exit(1)
        else:
            output_dir = os.path.abspath(args.output_directory)
            os.makedirs(output_dir, exist_ok=True)

        if args.parallel is not None:
            amount_cases = args.amount if args.amount is not None else 0
            amount_processes = max(1, args.parallel)
            gen = case_generator.parallel_interesting_case_file(
                config=config,
                scenario=scenario,
                processes=amount_processes,
                output_dir=output_dir,
                start_stop=False,
            )
            if amount_cases == 0:
                while True:
                    print(next(gen))
            else:
                for i in range(amount_cases):
                    print(next(gen))

        else:
            print(case_generator.generate_interesting_case(scenario))
    else:
        # TODO
        print("Not implemented yet")

    # This is not needed here but I don't know why.
    case_generator.terminate_processes()
