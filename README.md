# super-duper-chainsaw

Listing Photo Saver

This project provides a simple command line tool for downloading images from
real estate listing pages and organizing them in a folder structure derived from
the listing address and detected keywords.

Keyword tags for styles and features are defined in `tags.json`. Modify this file
to suit your needs without changing the code.

## Requirements

```
pip install -r requirements.txt
```

## Usage

Run the downloader with one or more listing URLs:

```
python listing_downloader.py <url1> <url2> ...
```

Images are stored under the `listings` directory by default. A `config.json`
file persists the chosen base directory and a `processed_urls.json` file
prevents re-downloading the same URL twice. Keyword tags are loaded from
`tags.json` and can be customized. Use `--delay` to control the pause
between requests. Images served as WebP are converted to JPEG automatically
to maximize compatibility.
