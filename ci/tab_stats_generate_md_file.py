#!/usr/bin/python3
"""
Script using the gathered data from the OSHP project "oshp-stats" to generate/update the 
markdown file "tab_statistics.md" with mermaid pie charts with differents statistics about HTTP security headers usage.

Source:
    https://mermaid-js.github.io/mermaid/#/pie
    https://github.com/oshp/oshp-stats/
"""
import sqlite3
import re
import json
import hashlib
from collections import Counter
from datetime import datetime
from pathlib import Path

# Constants
DEBUG = True
DATA_DB_FILE = "/tmp/data.db"
OSHP_SECURITY_HEADERS_FILE_lOCATION = "headers_add.json"
OSHP_SECURITY_HEADERS_EXTRA_FILE_LOCATION = "/tmp/oshp_headers_extra_to_include.txt"
MD_FILE = "../tab_statistics.md"
IMAGE_FOLDER_LOCATION = "../assets/tab_stats_generated_images"
TAB_MD_TEMPLATE = """---
title: statistics
displaytext: Statistics
layout: null
tab: true
order: 7
tags: headers
---

<!-- All the content of this file is generated by the script "ci/tab_stats_generate_md_file.py" -->

<!-- DO NOT EDIT IT MANUALLY -->

# Statistic about HTTP security response headers usage

<!-- markdown-link-check-disable -->

"""
SECTION_TEMPLATE = f"""
## %s

%s

![%s]({IMAGE_FOLDER_LOCATION.replace('../', '')}/%s)
"""
SECTION_TEMPLATE_NO_MERMAID_CODE = """
## %s

%s
"""

# Utility functions


def trace(msg):
    if DEBUG:
        print(f"[DEBUG] {msg}")


def prepare_generation_of_image_from_mermaid(mermaid_code, filename):
    trace(f"Call prepare_generation_of_image_from_mermaid() => {filename}")
    with open(f"{IMAGE_FOLDER_LOCATION}/{filename}.mmd", "w", encoding="utf-8") as f:
        f.write(mermaid_code + "\n")
    trace("Call end.")


def load_oshp_headers():
    trace("Call load_oshp_headers()")
    header_names = []
    trace(f"Call load_oshp_headers() :: Load and parse file {OSHP_SECURITY_HEADERS_FILE_lOCATION}")
    with open(OSHP_SECURITY_HEADERS_FILE_lOCATION, mode="r", encoding="utf-8") as f:
        data = json.load(f)
        http_headers = data["headers"]
    for http_header in http_headers:
        header_names.append(http_header["name"].lower())
    trace(f"Call load_oshp_headers() :: Load file {OSHP_SECURITY_HEADERS_EXTRA_FILE_LOCATION}")
    with open(OSHP_SECURITY_HEADERS_EXTRA_FILE_LOCATION, mode="r", encoding="utf-8") as f:
        http_headers = f.read()
    trace(f"Call load_oshp_headers() :: Parse file {OSHP_SECURITY_HEADERS_EXTRA_FILE_LOCATION}")
    for http_header in http_headers .split("\n"):
        header_names.append(http_header.lower().strip(" \n\r\t"))
    header_names = list(dict.fromkeys(header_names))
    header_names.sort()
    trace("Call end.")
    return header_names


def execute_query_against_data_db(sql_query):
    trace(f"Call execute_query_against_data_db() => {sql_query}")
    with sqlite3.connect(DATA_DB_FILE) as connection:
        curs = connection.cursor()
        curs.execute(sql_query)
        records = curs.fetchall()
        trace("Call end.")
        return records


def add_stats_section(title, description, chart_mermaid_code):
    trace(f"Call add_stats_section() => '{title}'")
    with open(MD_FILE, mode="a", encoding="utf-8") as f:
        if chart_mermaid_code is not None and len(chart_mermaid_code.strip()) > 0:
            base_image_filename = hashlib.sha1(title.encode("utf8")).hexdigest()
            prepare_generation_of_image_from_mermaid(chart_mermaid_code, base_image_filename)
            md_code = SECTION_TEMPLATE % (title, description, base_image_filename, f"{base_image_filename}.png")
        else:
            md_code = SECTION_TEMPLATE_NO_MERMAID_CODE % (title, description)
        f.write(f"{md_code}\n")
    trace("Call end.")


def init_stats_file():
    trace("Call init_stats_file()")
    with open(MD_FILE, mode="w", encoding="utf-8") as f:
        cdate = datetime.now().strftime("%m/%d/%Y at %H:%M:%S")
        f.write(TAB_MD_TEMPLATE)
        f.write("\n\n")
        f.write(f"📅 Last update: {cdate} - Domains analyzed count: {get_domains_count()}.\n")
    trace("Call end.")


def get_domains_count():
    return len(execute_query_against_data_db("select distinct domain from stats"))


def get_pie_chart_code(title, dataset_tuples):
    # code = f"pie title {title}\n"
    code = f"pie\n"
    for dataset_tuple in dataset_tuples:
        # Note: Mermaid use integer value when rendering
        code += f"\t\"{dataset_tuple[0]}\" : {round(dataset_tuple[1], 2)}\n"
    return code


def csp_contain_unsafe_expression(csp_policy):
    contain_unsafe_expression = False
    # Determine if a CSP policy contains (default-src|script-src|script-src-elem|script-src-attr|style-src) directives using (unsafe-inline|unsafe-hashes|unsafe-eval) expressions
    # Based on "https://report-uri.com/home/generate" generator allowed instructions for CSP directives
    exp_all_unsafe_expressions = r'(unsafe-inline|unsafe-hashes|unsafe-eval)'
    exp_style_unsafe_expressions = r'(unsafe-inline|unsafe-hashes)'
    exp_directive_name_allowing_all_unsafe_expressions = r'(default-src|script-src|script-src-elem|script-src-attr)'
    directives = csp_policy.split(";")
    for directive in directives:
        if len(re.findall(exp_directive_name_allowing_all_unsafe_expressions, directive)) > 0 and len(re.findall(exp_all_unsafe_expressions, directive)) > 0:
            contain_unsafe_expression = True
            break
        elif directive.strip().startswith("style-src") and len(re.findall(exp_style_unsafe_expressions, directive)) > 0:
            contain_unsafe_expression = True
            break
    return contain_unsafe_expression


# Functions in charge of generate stats sections


def compute_header_global_usage(header_name):
    title = f"Global usage of header '{header_name}'"
    description = f"Provide the distribution of usage of the header '{header_name}' across all domains analyzed."
    # Prevent the case in which a domain specify X times the same headers...
    query = f"select distinct domain from stats where lower(http_header_name) = '{header_name}'"
    count_of_domains_using_the_header = len(
        execute_query_against_data_db(query))
    domains_count = get_domains_count()
    percentage_of_domains_using_the_header = (
        count_of_domains_using_the_header * 100) / domains_count
    dataset_tuples = [("Using it", percentage_of_domains_using_the_header),
                      ("Not using it", (100-percentage_of_domains_using_the_header))]
    pie_chart_code = get_pie_chart_code(title, dataset_tuples)
    add_stats_section(title, description, pie_chart_code)


def compute_insecure_framing_configuration_global_usage():
    header_name = "x-frame-options"
    title = f"Global usage of insecure framing configuration via the header '{header_name}'"
    description = f"Provide the distribution of usage of the header '{header_name}' across all domains analyzed with a insecure framing configuration: value different from `DENY` or `SAMEORIGIN` including unsupported values."
    query = f"select count(*) from stats where lower(http_header_name) = '{header_name}' and lower(http_header_value) not in ('deny','sameorigin')"
    count_of_domains = execute_query_against_data_db(query)[0][0]
    domains_count = get_domains_count()
    percentage_of_domains = (count_of_domains * 100) / domains_count
    dataset_tuples = [("Insecure conf", percentage_of_domains),
                      ("Secure conf", (100-percentage_of_domains))]
    pie_chart_code = get_pie_chart_code(title, dataset_tuples)
    add_stats_section(title, description, pie_chart_code)


def compute_hsts_preload_global_usage():
    header_name = "strict-transport-security"
    title = "Global usage of the Strict Transport Security 'preload' feature"
    description = f"Provide the distribution of usage of the '[preload](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Strict-Transport-Security#preloading_strict_transport_security)' feature for the header '{header_name}' across all domains analyzed."
    query = f"select count(*) from stats where lower(http_header_name) = '{header_name}' and lower(http_header_value) not like '%preload%'"
    count_of_domains = execute_query_against_data_db(query)[0][0]
    domains_count = get_domains_count()
    percentage_of_domains = (count_of_domains * 100) / domains_count
    dataset_tuples = [("Using it", percentage_of_domains),
                      ("Not using it", (100-percentage_of_domains))]
    pie_chart_code = get_pie_chart_code(title, dataset_tuples)
    add_stats_section(title, description, pie_chart_code)


def compute_secure_headers_global_usage():
    title = "Global usage of secure headers"
    description = f"Provide the distribution of usage of secure headers across all domains analyzed."
    query = "select count(domain) from stats where http_header_name is NULL"
    count_of_domains = execute_query_against_data_db(query)[0][0]
    domains_count = get_domains_count()
    percentage_of_domains = (count_of_domains * 100) / domains_count
    dataset_tuples = [("Not using them", percentage_of_domains),
                      ("Using them", (100-percentage_of_domains))]
    pie_chart_code = get_pie_chart_code(title, dataset_tuples)
    add_stats_section(title, description, pie_chart_code)


def compute_insecure_referrer_configuration_global_usage():
    header_name = "referrer-policy"
    title = f"Global usage of insecure referrer configuration via the header '{header_name}'"
    description = f"Provide the distribution of usage of the header '{header_name}' across all domains analyzed with a insecure referrer configuration: value set to `unsafe-url` or `no-referrer-when-downgrade`.\n\n`no-referrer-when-downgrade` was included because it send origin, path, and querystring when the protocol security level stays the same (HTTPS is very often in place)."
    query = f"select count(*) from stats where lower(http_header_name) = '{header_name}' and lower(http_header_value) in ('unsafe-url','no-referrer-when-downgrade')"
    count_of_domains = execute_query_against_data_db(query)[0][0]
    domains_count = get_domains_count()
    percentage_of_domains = (count_of_domains * 100) / domains_count
    dataset_tuples = [("Insecure conf", percentage_of_domains),
                      ("Secure conf", (100-percentage_of_domains))]
    pie_chart_code = get_pie_chart_code(title, dataset_tuples)
    add_stats_section(title, description, pie_chart_code)


def compute_hsts_average_maxage_global_usage():
    title = "Global common 'max-age' values of the Strict Transport Security header"
    query = "select lower(http_header_value) from stats where lower(http_header_name) = 'strict-transport-security' and lower(http_header_value) like '%max-age=%'"
    header_values = execute_query_against_data_db(query)
    expr = r'max-age\s*=\s*(\-?"?\d+"?)'
    # Gather values for max-age attribute
    values = []
    for header_value in header_values:
        v = header_value[0].strip('\n\r\t').replace('"', '')
        matches = re.findall(expr, v)
        if len(matches) > 0:
            values.append(int(matches[0]))
    # Find the most popular one
    occurences = Counter(values)
    maxage_most_popular_value = 0
    current_max_occurence_count = 0
    for maxage_value, occurence_count in occurences.items():
        if occurence_count > current_max_occurence_count:
            current_max_occurence_count = occurence_count
            maxage_most_popular_value = maxage_value
    description = f"* Most common value used is {maxage_most_popular_value} seconds ({round(maxage_most_popular_value/60)} minutes) across all domains analyzed."
    description += f"\n* Maximum value used is {max(values)} seconds ({round(max(values)/60)} minutes) across all domains analyzed."
    description += f"\n* Minimum value used is {min(values)} seconds ({round(min(values)/60)} minutes) across all domains analyzed."
    add_stats_section(title, description, None)


def compute_csp_using_directives_with_unsafe_expressions_configuration_global_usage():
    header_name = "content-security-policy"
    title = f"Global usage of content security policy with directives allowing unsafe expressions"
    description = f"Provide the distribution of content security policy allowing unsafe expressions across all domains analyzed.\n\nDetermine if a CSP policy contains `(default-src|script-src|script-src-elem|script-src-attr|style-src)` directives using `(unsafe-inline|unsafe-hashes|unsafe-eval)` expressions.\n\nBased on [Report-URI CSP](https://report-uri.com/home/generate) generator allowed instructions for CSP directives."
    query = f"select lower(http_header_value) from stats where lower(http_header_name) like '{header_name}%' and lower(http_header_value) like '%unsafe%'"
    header_values = execute_query_against_data_db(query)
    count_of_domains = 0
    for header_value in header_values:
        if csp_contain_unsafe_expression(header_value[0]):
            count_of_domains += 1
    domains_count = get_domains_count()
    percentage_of_domains = (count_of_domains * 100) / domains_count
    dataset_tuples = [("Using unsafe", percentage_of_domains),
                      ("Not using unsafe", (100-percentage_of_domains))]
    pie_chart_code = get_pie_chart_code(title, dataset_tuples)
    add_stats_section(title, description, pie_chart_code)


if __name__ == "__main__":
    trace("Clear PNG files")
    for path in Path(IMAGE_FOLDER_LOCATION).glob("*.png"):
        path.unlink()
    trace("Clear MMD files")
    for path in Path(IMAGE_FOLDER_LOCATION).glob("*.mmd"):
        path.unlink()
    oshp_headers = load_oshp_headers()
    init_stats_file()
    compute_secure_headers_global_usage()
    for header_name in oshp_headers:
        compute_header_global_usage(header_name)
    compute_insecure_framing_configuration_global_usage()
    compute_insecure_referrer_configuration_global_usage()
    compute_hsts_preload_global_usage()
    compute_hsts_average_maxage_global_usage()
    compute_csp_using_directives_with_unsafe_expressions_configuration_global_usage()
