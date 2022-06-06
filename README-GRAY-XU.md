# Dead Change Log

Authors: Gavin Gray, Pengcheng Xu

This log is to record changes throughout the AST project as things get changed. This is not a replacement for good Git commit messages but can serve as an outlet for additional information.

:exclamation: please remove me at the end of the project.

## Installing YARPGen

`yarpgen` installation is very simple and can be followed from their [GitHub](https://github.com/intel/yarpgen).

YARPGen generates a directory of files to be built together, unlike CSmith which creates a standalone source.  This is handled by modifications to the tool to concatenate the source code together.

### Two different versions of YARPGen

Since the `main` branch of YARPGen includes the experimental loop generation features as put in their paper, we find it may be beneficial to test both versions (`v1` and `main`).  The build instructions should be the same for the two versions.

Note that two versions accept different commandline arguments.  The DCE tool is modified to detect the version of YARPGen in runtime and adjust accordingly.  Thus, to switch to a different version of YARPGen, simply rebuild yarpgen with the desired version.

## Workflow and Running `deaddocker`

In order to edit source files while still benefiting of the system environment provded by the Docker container, I (Gavin) suggest running the container with the following:

```console
% docker run -it -v deadpersistent:/persistent \
    --mount type=bind,source="$(pwd)",target=/home/leroy \
    deaddocker
```

To handle permission problems, create a new group with the same pid as your _user group_ inside the container, and add the `dead` user to that group.

```console
# sudo groupadd -g 1024 shared # assuming $(id -g) on host gave 1024
# sudo gpasswd -a dead shared
```

Exit the container, and then re-attach with the following:

```console
% sudo docker ps -a # remember the container id; assume we have 5299 here
% sudo docker start 5299 && sudo docker attach 5299
# id # verify that we now have shared(1024) in the group list
```

When run from within the `dead` environment, this will create a bind mount in the container directory `/home/leroy` which I suggest switching to for running tests. This is especially usefull if you are using Emacs[^1] and have multiple windows open.

Once you have the Docker container running and you are in the working directory. Run the sript `./setup.scm` which will setup YARPGen for you and put it in the right(?) place.

If something in the script goes wrong, and you need to only run *parts* of it later, you can invoke it as follows: `./setup.scm <part-name>* ...` inserting the related step name(s) which will run only the specified steps in the specified order.

## Source-level statistics

We collect the statistics of ratio of DCE markers into a file, `yarpgen-stats.txt` (or `yarpgen_v1-stats.txt`) for further analysis.  For comparison, we collect the same statistics for CSmith in `csmith-stats.txt`.  The statistics are then further processed to compare the effectiveness of both generators for DCE.

## Changes

Anything notable to document? Put it in the source! But feel free to also list things here that
are more informal. This is also a good place to list the hacks we've done so that they can be tracked reversed/fixed at some point.

- In the files `utils.py` and `init.py` I've changed the lines `Path.home() => Path('/home/leroy')` this reflecting the development dir I've set up. This is obviouisly a hack, I tried changing the default home directory for the user *dead* via `usermod -d /home/leroy dead` but this still searched in the old directory.

## TODO

- [x] Add a `run_yarpgen` function in `generator.py`.
- [x] Figure out how to include dead flags within a directory.
- [x] Concatenate all source files
- [x] How can we gather usefull statistics for the report?

[^1]: If not, you should be :kissing_smiling_eyes:.
