# -*- coding: utf-8 -*-
"""打包配置。

元数据故意写在 setup.py 而不是 pyproject 的 [project] 表里，
因为老一点的 setuptools（<61）读不了 [project]。这样两边都能装。
"""

from setuptools import setup

setup(
    name="mahjong-math-kernel",
    version="1.0.0",
    description="麻将数学内核：把向听/进张/番种/点数/概率/期望值算出来，并标明哪些是模型",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="mahjong-math-kernel contributors",
    author_email="noreply@users.noreply.github.com",
    license="MIT",
    url="https://github.com/ququdu/mahjong-math-kernel",
    python_requires=">=3.9",
    packages=[
        "mahjong_kernel",
        "mahjong_kernel.rulesets",
        "mahjong_kernel.api",
        "vision",
    ],
    package_data={"": ["*.md", "*.json"]},
    install_requires=[],
    extras_require={
        # 只有截图识别 / 实时模式需要
        "vision": ["Pillow>=9.0", "numpy>=1.21"],
        # 更快的截屏后端（可选）
        "fast-capture": ["mss>=7.0"],
    },
    entry_points={
        "console_scripts": [
            "mahjong-kernel=mahjong_kernel.api.cli:main",
            "mahjong-vision=vision.cli:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Games/Entertainment :: Board Games",
        "Topic :: Scientific/Engineering :: Mathematics",
    ],
    zip_safe=False,
)
