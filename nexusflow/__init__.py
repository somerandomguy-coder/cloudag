"""Compatibility wrapper: forwards nexusflow imports to cloudag."""

import sys
import cloudag
import cloudag.api
import cloudag.core
import cloudag.executors
import cloudag.models
import cloudag.storage

from cloudag import *  # noqa: F401, F403

sys.modules["nexusflow.api"] = cloudag.api
sys.modules["nexusflow.core"] = cloudag.core
sys.modules["nexusflow.executors"] = cloudag.executors
sys.modules["nexusflow.models"] = cloudag.models
sys.modules["nexusflow.storage"] = cloudag.storage
