from setuptools import setup, find_packages

setup(
    name="copyclip",
    version="1.0.0",
    author="Samuel Dario",
    author_email="correo@samueldar.io",
    description="Copy file contents from a directory to the clipboard.",
    packages=find_packages(),
    py_modules=["copyclip"],  # Nombre del script sin extensión
    include_package_data=True,  # Incluir archivos declarados en MANIFEST.in
    package_data={
        '': ['.copyclipignore'],  # Archivos específicos
    },
    install_requires=[
        "pyperclip",
        "tqdm",
        "gitignore-parser"
    ],
    entry_points={
        "console_scripts": [
            "copyclip=copyclip:main",  # El nombre del comando y la función principal
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)

