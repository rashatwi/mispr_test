import os

import setuptools

module_dir = os.path.dirname(os.path.abspath(__file__))

setuptools.setup(
    name="mispr",
    version="0.0.1",
    author="Rasha Atwi, Matthew Bliss",
    author_email="rasha.atwi@stonybrook.edu, matthew.bliss@stonybrook.edu",
    description="mispr contains FireWorks workflows for Materials Science",
    long_description=open(os.path.join(module_dir, "README.md")).read(),
    url="https://github.com/tufts-university-rajput-lab/mispr",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status ::  2 - Pre-Alpha",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Information Technology",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering",
    ],
    python_requires=">=3.6",
    package_data={"": ["gaussian/data/*.bib"]},
)