# engines/journey-core/__init__.py
#
# WHAT: Package initializer for the journey-core engine.
# WHY:  Makes the directory a proper Python package so imports like
#       `from engines.journey_core.generator import generate_journey`
#       work from any test or caller.
# BREAKS IF DELETED: Import paths break across the project.
