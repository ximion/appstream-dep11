# Debian AppStream DEP-11 tools

This Python module allows you to generate and validate DEP-11 metadata,
which is Debians implementation of AppStream.
The tools can be used standalone, or be integrated with other services.

You can find out more about DEP-11 YAML at the [Debian Wiki](https://wiki.debian.org/DEP-11), and more about
AppStream distro metadata at [Freedesktop](http://www.freedesktop.org/software/appstream/docs/chap-DistroData.html#sect-AppStream-ASXML).

## Dependencies
In order to use AppStream-DEP11, the following components are needed:
 * Python 3 (ideally >> 3.4.3)
 * GIR for RSvg-2.0
 * python-apt
 * python-cairo
 * python-gi
 * Jinja2
 * python-lmdb
 * python-lxml
 * python-pil
 * Matplotlib
 * Voluptuous
 * PyYAML
 * Pygments (optional)

To install all dependencies on Debian systems, use
```ShellSession
sudo apt install gir1.2-rsvg-2.0 python3-apt python3-cairo python3-gi python3-jinja2 python3-lmdb \
    python3-gi-cairo python3-lxml python3-pil python3-voluptuous python3-yaml python3-matplotlib python3-pygments
```

## How to use

### Generating distro metadata
To generate AppStream distribution metadata for your repository, create a local
mirror of the repository first.
Then create a new folder, and write a `dep11-config.yml` configuration file for the
metadata generator. A minimal configuration file may look like this:
```YAML
ArchiveRoot: /srv/archive.tanglu.org/tanglu/
MediaBaseUrl: http://metadata.tanglu.org/dep11/media
HtmlBaseUrl: http://metadata.tanglu.org/dep11/hints_html/
Suites:
  chromodoris:
    components:
      - main
      - contrib
    architectures:
      - amd64
      - i386
  chromodoris-updates:
    dataPriority: 10
    components:
      - main
      - contrib
    architectures:
      - amd64
      - i386
```

Key | Comment
------------ | -------------
ArchiveRoot | A local URL to the mirror of your archive, containing the dists/ and pool/ directories
MediaBaseUrl | The http or https URL which should be used in the generated metadata to fetch media like screenshots or icons
HtmlBaseUrl | The http or https URL to the web location where the HTML hints will be published. (This setting is optional, but recommended)
Suites | A list of suites which should be recognized by the generator. Each suite has the components and architectures which should be seached for metadata as children.

After the config file has been written, you can generate the metadata as follows:
```Bash
cd /srv/dep11/workspace # path where the dep11-config.yml file is located
dep11-generator process . chromodoris # replace "chromodoris" with the name of the suite you want to analyze
```
The generator is assuming you have enough memory on your machine to cache stuff.
Resulting metadata will be placed in `export/data/`, machine-readable issue-hints can be found in `export/hints/` and the processed
screenshots are located in `export/media/`.

### Validating metadata
Just run `dep11-validate <dep11file>.yml.gz` to check a file for spec-compliance.
