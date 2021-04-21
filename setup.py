from setuptools import setup

long_description = "Finna make pretty pictures"

setup(
    name = "VAE",
    version = "dev",
    description = long_description,

    url = "https://github.com/evaneill/vae",

    install_requires = [
        "torch>=1.8.0",
        "pandas>=1.2.4",
        "numpy>=1.20.0",
    ]
)