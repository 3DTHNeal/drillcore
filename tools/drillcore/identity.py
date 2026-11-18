"""What this tool is called, in the one place that says so.

Everything that would otherwise repeat the name reads it from here: the environment variable and pointer file that
name the workspace, the database's file name, and the port the review page is served on.
tools/tests/test_identity.py holds the rest of the repository to these values.
"""

# The name people read.
NAME = "Drillcore"
# The name programs use: the package, the command and the start of each file name below.
SLUG = "drillcore"
# Names the workspace for one run. It wins over the pointer file.
HOME_VARIABLE = "DRILLCORE_HOME"
# A file in the clone, never committed, whose first line names the workspace.
HOME_POINTER = ".drillcore-home"
# The file that makes a folder a workspace.
CONFIG = "workspace.toml"
# The database, in the workspace's data/ folder.
DATABASE = "drillcore.db"
# Where `review` serves its page, on this computer only, unless the port is taken.
PORT = 8801
