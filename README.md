# Debian AppStream DEP-11 tools

This Python module allows you to generate and validate DEP-11 metadata,
which is Debians implementation of AppStream.
The tools can be used standalone, or be integrated with other services.

You can find out more about DEP-11 YAML at the [Debian Wiki](https://wiki.debian.org/DEP-11), and more about
AppStream distro metadata at [Freedesktop](http://www.freedesktop.org/software/appstream/docs/chap-DistroData.html#sect-AppStream-ASXML).

## Dependencies
In order to use AppStream-DEP11, the following components are needed:
 * Python 3 (ideally >> 3.4.3)
 * GIR for RSvg-2.0,
 * python-apt,
 * python-cairo,
 * python-gi,
 * Jinja2,
 * python-kyotocabinet,
 * python-lxml,
 * python-pil,
 * Voluptuous,
 * PyYAML

To install all dependencies on Debian systems, use
```ShellSession
sudo apt install gir1.2-rsvg-2.0 python3-apt python3-cairo python3-gi python3-jinja2 \
    python3-kyotocabinet python3-lxml python3-pil python3-voluptuous python3-yaml
```
