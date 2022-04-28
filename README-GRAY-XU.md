# Dead Change Log

Authors: Gavin Gray, Pengcheng Xu 

This log is to record changes throughout the AST project as things get changed. This is not a replacement for good Git commit messages but can serve as an outlet for additional information.

:exclamation: please remove me at the end of the project.

## Installing YARPGen

`yarpgen` installation is very simple and can be followed from their [GitHub](https://github.com/intel/yarpgen). 

YARPGen generates a directory of files to be built together, unlike Csmith which creates a standalone source. 

## Workflow and Running `deaddocker`

In order to edit source files while still benefiting of the system environment provded by the Docker container, I (Gavin) suggest running the container with the following:

```bash
 % docker run -it -v deadpersistent:/persistent \         
    --mount type=bind,source="$(pwd)",target=/home/leroy \
    deaddocker
```

When run from within the `dead` environment, this will create a bind mount in the container directory `/home/leroy` which I suggest switching to for running tests. This is especially usefull if you are using Emacs[^1] and have multiple windows open.

Once you have the Docker container running and you are in the working directory. Run the sript `./setup.scm` which will setup YARPGen for you and put it in the right(?) place.

If something in the script goes wrong, and you need to only run *parts* of it later, you can invoke it as follows: `./setup.scm <part-name>* ...` inserting the related step name(s) which will run only the specified steps in the specified order.

## Changes 

Anything notable to document? Put it in the source! But feel free to also list things here that 
are more informal.

## TODO

[ ] Add a `run_yarpgen` function in `generator.py`.
[ ] Figure out how to include dead flags within a directory.
[ ] Compile all `*.(c|cpp)*` files in a directory instead of a single source.
[ ] How can we gather usefull statistics for the report?

[^1]: If not, you should be :kissing_smiling_eyes:.
