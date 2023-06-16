## Site data

This directory contains the site data needed to run the website in a modular fashion. In config, `data_dir` controls where the sitedata should be served from. The old `sitedata` folder is deprecated.

Within the `data_dir`, the files are organized as follows:

- `configs`: Location of all site related configs in `.yml` format. 
- `data`: Location of all site data (such as paper names, paper recommendations etc)
- `pages`: Individual page content, separated in page name directories. The page contents should be provided in Markdown (`.md` format) so that it is easily readable and maintainable.

The data loading logic is provided in `load_site_data.py` file. Specifically, when it is invoked, it first reads the `configs` for all pages, then loads the associated data from `data` and `pages` directories.