import unittest
import sys
from pathlib import Path

def run_tests():
    """
    Discover and run all tests in the 'tests/' directory.
    """
    # Add the root directory to the Python path
    # This allows the tests to import the main application modules
    root_dir = Path(__file__).parent
    sys.path.insert(0, str(root_dir))

    # Create a TestLoader instance
    loader = unittest.TestLoader()

    # Discover tests in the 'tests' directory
    suite = loader.discover(start_dir='tests')

    # Create a TestRunner instance
    runner = unittest.TextTestRunner(verbosity=2)

    # Run the tests
    result = runner.run(suite)

    # Exit with a non-zero status code if any tests failed
    if not result.wasSuccessful():
        sys.exit(1)

if __name__ == '__main__':
    run_tests()
