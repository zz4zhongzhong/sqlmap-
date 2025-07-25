#!/usr/bin/env python

"""
Copyright (c) 2006-2025 sqlmap developers (https://sqlmap.org)
See the file 'LICENSE' for copying permission
"""

from __future__ import print_function

import os
import re
import shlex
import sys

try:
    from optparse import OptionError as ArgumentError
    from optparse import OptionGroup
    from optparse import OptionParser as ArgumentParser
    from optparse import SUPPRESS as SUPPRESS

    ArgumentParser.add_argument = ArgumentParser.add_option

    def _add_argument_group(self, *args, **kwargs):
        return self.add_option_group(OptionGroup(self, *args, **kwargs))

    ArgumentParser.add_argument_group = _add_argument_group

    def _add_argument(self, *args, **kwargs):
        return self.add_option(*args, **kwargs)

    OptionGroup.add_argument = _add_argument

except ImportError:
    from argparse import ArgumentParser
    from argparse import ArgumentError
    from argparse import SUPPRESS

finally:
    def get_actions(instance):
        for attr in ("option_list", "_group_actions", "_actions"):
            if hasattr(instance, attr):
                return getattr(instance, attr)

    def get_groups(parser):
        return getattr(parser, "option_groups", None) or getattr(parser, "_action_groups")

    def get_all_options(parser):
        retVal = set()

        for option in get_actions(parser):
            if hasattr(option, "option_strings"):
                retVal.update(option.option_strings)
            else:
                retVal.update(option._long_opts)
                retVal.update(option._short_opts)

        for group in get_groups(parser):
            for option in get_actions(group):
                if hasattr(option, "option_strings"):
                    retVal.update(option.option_strings)
                else:
                    retVal.update(option._long_opts)
                    retVal.update(option._short_opts)

        return retVal

from lib.core.common import checkOldOptions
from lib.core.common import checkSystemEncoding
from lib.core.common import dataToStdout
from lib.core.common import expandMnemonics
from lib.core.common import getSafeExString
from lib.core.compat import xrange
from lib.core.convert import getUnicode
from lib.core.data import cmdLineOptions
from lib.core.data import conf
from lib.core.data import logger
from lib.core.defaults import defaults
from lib.core.dicts import DEPRECATED_OPTIONS
from lib.core.enums import AUTOCOMPLETE_TYPE
from lib.core.exception import SqlmapShellQuitException
from lib.core.exception import SqlmapSilentQuitException
from lib.core.exception import SqlmapSyntaxException
from lib.core.option import _createHomeDirectories
from lib.core.settings import BASIC_HELP_ITEMS
from lib.core.settings import DUMMY_URL
from lib.core.settings import IGNORED_OPTIONS
from lib.core.settings import INFERENCE_UNKNOWN_CHAR
from lib.core.settings import IS_WIN
from lib.core.settings import MAX_HELP_OPTION_LENGTH
from lib.core.settings import VERSION_STRING
from lib.core.shell import autoCompletion
from lib.core.shell import clearHistory
from lib.core.shell import loadHistory
from lib.core.shell import saveHistory
from thirdparty.six.moves import input as _input

def cmdLineParser(argv=None):
    """
    This function parses the command line parameters and arguments
    """

    if not argv:
        argv = sys.argv

    checkSystemEncoding()

    # Reference: https://stackoverflow.com/a/4012683 (Note: previously used "...sys.getfilesystemencoding() or UNICODE_ENCODING")
    _ = getUnicode(os.path.basename(argv[0]), encoding=sys.stdin.encoding)

    usage = "%s%s [options]" % ("%s " % os.path.basename(sys.executable) if not IS_WIN else "", "\"%s\"" % _ if " " in _ else _)
    parser = ArgumentParser(usage=usage)

    try:
        parser.add_argument("--hh", dest="advancedHelp", action="store_true",
            help="Show advanced help message and exit;展示高级帮助信息并退出")

        parser.add_argument("--version", dest="showVersion", action="store_true",
            help="Show program's version number and exit;展示程序版本号并退出")

        parser.add_argument("-v", dest="verbose", type=int,
            help="Verbosity level: 0-6 (default %d);详细程度级别: 0-6 (默认%d)" % (defaults.verbose, defaults.verbose))

        # Target options
        target = parser.add_argument_group("Target", "At least one of these options has to be provided to define the target(s);至少需要提供一个选项来定义目标(s)")

        target.add_argument("-u", "--url", dest="url",
            help="Target URL (e.g. \"http://www.site.com/vuln.php?id=1\");目标URL(例如: \"http://www.site.com/vuln.php?id=1\")")

        target.add_argument("-d", dest="direct",
            help="Connection string for direct database connection;直接数据库连接字符串")

        target.add_argument("-l", dest="logFile",
            help="Parse target(s) from Burp or WebScarab proxy log file;从Burp或WebScarab代理日志文件中解析目标(s)")

        target.add_argument("-m", dest="bulkFile",
            help="Scan multiple targets given in a textual file;扫描多个目标，给定一个文本文件")

        target.add_argument("-r", dest="requestFile",
            help="Load HTTP request from a file;从文件加载HTTP请求")

        target.add_argument("-g", dest="googleDork",
            help="Process Google dork results as target URLs;将Google dork结果作为目标URL处理")

        target.add_argument("-c", dest="configFile",
            help="Load options from a configuration INI file;从配置INI文件加载选项")

        # Request options
        request = parser.add_argument_group("Request", "These options can be used to specify how to connect to the target URL;这些选项可以用于指定如何连接到目标URL")

        request.add_argument("-A", "--user-agent", dest="agent",
            help="HTTP User-Agent header value;HTTP User-Agent头值")

        request.add_argument("-H", "--header", dest="header",
            help="Extra header (e.g. \"X-Forwarded-For: 127.0.0.1\");额外头(例如: \"X-Forwarded-For: 127.0.0.1\")")

        request.add_argument("--method", dest="method",
            help="Force usage of given HTTP method (e.g. PUT);强制使用给定的HTTP方法(例如: PUT)")

        request.add_argument("--data", dest="data",
            help="Data string to be sent through POST (e.g. \"id=1\");通过POST发送的数据字符串(例如: \"id=1\")")

        request.add_argument("--cookie", dest="cookie",
            help="HTTP Cookie header value (e.g. \"PHPSESSID=a8d127e..\");HTTP Cookie头值(例如: \"PHPSESSID=a8d127e..\")")

        request.add_argument("--cookie-del", dest="cookieDel",
            help="Character used for splitting cookie values (e.g. ;);用于分割cookie值的字符(例如: ;)")

        request.add_argument("--live-cookies", dest="liveCookies",
            help="Live cookies file used for loading up-to-date values;用于加载最新值的实时cookies文件")

        request.add_argument("--load-cookies", dest="loadCookies",
            help="File containing cookies in Netscape/wget format;包含Netscape/wget格式cookies的文件")

        request.add_argument("--drop-set-cookie", dest="dropSetCookie", action="store_true",
            help="Ignore Set-Cookie header from response;忽略响应中的Set-Cookie头")

        request.add_argument("--http2", dest="http2", action="store_true",
            help="Use HTTP version 2 (experimental);使用HTTP版本2(实验性)")

        request.add_argument("--mobile", dest="mobile", action="store_true",
            help="Imitate smartphone through HTTP User-Agent header;通过HTTP User-Agent头模拟智能手机")

        request.add_argument("--random-agent", dest="randomAgent", action="store_true",
            help="Use randomly selected HTTP User-Agent header value;使用随机选择的HTTP User-Agent头值")

        request.add_argument("--host", dest="host",
            help="HTTP Host header value;HTTP Host头值")

        request.add_argument("--referer", dest="referer",
            help="HTTP Referer header value;HTTP Referer头值")

        request.add_argument("--headers", dest="headers",
            help="Extra headers (e.g. \"Accept-Language: fr\\nETag: 123\");额外头(例如: \"Accept-Language: fr\\nETag: 123\")")

        request.add_argument("--auth-type", dest="authType",
            help="HTTP authentication type (Basic, Digest, Bearer, ...);HTTP认证类型(Basic, Digest, Bearer, ...)")

        request.add_argument("--auth-cred", dest="authCred",
            help="HTTP authentication credentials (name:password);HTTP认证凭证(用户名:密码)")

        request.add_argument("--auth-file", dest="authFile",
            help="HTTP authentication PEM cert/private key file;HTTP认证PEM证书/私钥文件")

        request.add_argument("--abort-code", dest="abortCode",
            help="Abort on (problematic) HTTP error code(s) (e.g. 401);在(问题)HTTP错误代码(例如: 401)上中止")

        request.add_argument("--ignore-code", dest="ignoreCode",
            help="Ignore (problematic) HTTP error code(s) (e.g. 401);忽略(问题)HTTP错误代码(例如: 401)")

        request.add_argument("--ignore-proxy", dest="ignoreProxy", action="store_true",
            help="Ignore system default proxy settings;忽略系统默认代理设置")

        request.add_argument("--ignore-redirects", dest="ignoreRedirects", action="store_true",
            help="Ignore redirection attempts;忽略重定向尝试")

        request.add_argument("--ignore-timeouts", dest="ignoreTimeouts", action="store_true",
            help="Ignore connection timeouts;忽略连接超时")

        request.add_argument("--proxy", dest="proxy",
            help="Use a proxy to connect to the target URL;使用代理连接到目标URL")

        request.add_argument("--proxy-cred", dest="proxyCred",
            help="Proxy authentication credentials (name:password);代理认证凭证(用户名:密码)")

        request.add_argument("--proxy-file", dest="proxyFile",
            help="Load proxy list from a file;从文件加载代理列表")

        request.add_argument("--proxy-freq", dest="proxyFreq", type=int,
            help="Requests between change of proxy from a given list;从给定列表更改代理的请求")

        request.add_argument("--tor", dest="tor", action="store_true",
            help="Use Tor anonymity network;使用Tor匿名网络")

        request.add_argument("--tor-port", dest="torPort",
            help="Set Tor proxy port other than default;设置Tor代理端口(默认端口以外的端口)")

        request.add_argument("--tor-type", dest="torType",
            help="Set Tor proxy type (HTTP, SOCKS4 or SOCKS5 (default));设置Tor代理类型(HTTP, SOCKS4或SOCKS5(默认))")

        request.add_argument("--check-tor", dest="checkTor", action="store_true",
            help="Check to see if Tor is used properly;检查是否正确使用Tor")

        request.add_argument("--delay", dest="delay", type=float,
            help="Delay in seconds between each HTTP request;每个HTTP请求之间的延迟(秒)")

        request.add_argument("--timeout", dest="timeout", type=float,
            help="Seconds to wait before timeout connection (default %d);等待连接超时前的秒数(默认%d)" % (defaults.timeout, defaults.timeout))

        request.add_argument("--retries", dest="retries", type=int,
            help="Retries when the connection timeouts (default %d);连接超时时的重试次数(默认%d)" % (defaults.retries, defaults.retries))

        request.add_argument("--retry-on", dest="retryOn",
            help="Retry request on regexp matching content (e.g. \"drop\");在正则表达式匹配内容时重试请求(例如: \"drop\")")

        request.add_argument("--randomize", dest="rParam",
            help="Randomly change value for given parameter(s);随机更改给定参数的值")

        request.add_argument("--safe-url", dest="safeUrl",
            help="URL address to visit frequently during testing;在测试期间频繁访问的URL地址")

        request.add_argument("--safe-post", dest="safePost",
            help="POST data to send to a safe URL;发送给安全URL的POST数据")

        request.add_argument("--safe-req", dest="safeReqFile",
            help="Load safe HTTP request from a file;从文件加载安全HTTP请求")

        request.add_argument("--safe-freq", dest="safeFreq", type=int,
            help="Regular requests between visits to a safe URL;访问安全URL的常规请求")

        request.add_argument("--skip-urlencode", dest="skipUrlEncode", action="store_true",
            help="Skip URL encoding of payload data;跳过有效负载数据的URL编码")

        request.add_argument("--csrf-token", dest="csrfToken",
            help="Parameter used to hold anti-CSRF token;用于持有反CSRF令牌的参数")

        request.add_argument("--csrf-url", dest="csrfUrl",
            help="URL address to visit for extraction of anti-CSRF token;访问用于提取反CSRF令牌的URL地址")

        request.add_argument("--csrf-method", dest="csrfMethod",
            help="HTTP method to use during anti-CSRF token page visit;在访问反CSRF令牌页面时使用的HTTP方法")

        request.add_argument("--csrf-data", dest="csrfData",
            help="POST data to send during anti-CSRF token page visit;在访问反CSRF令牌页面时发送的POST数据")

        request.add_argument("--csrf-retries", dest="csrfRetries", type=int,
            help="Retries for anti-CSRF token retrieval (default %d);反CSRF令牌检索的重试次数(默认%d)" % (defaults.csrfRetries, defaults.csrfRetries))

        request.add_argument("--force-ssl", dest="forceSSL", action="store_true",
            help="Force usage of SSL/HTTPS;强制使用SSL/HTTPS")

        request.add_argument("--chunked", dest="chunked", action="store_true",
            help="Use HTTP chunked transfer encoded (POST) requests;使用HTTP分块传输编码(POST)请求")

        request.add_argument("--hpp", dest="hpp", action="store_true",
            help="Use HTTP parameter pollution method;使用HTTP参数污染方法")

        request.add_argument("--eval", dest="evalCode",
            help="Evaluate provided Python code before the request (e.g. \"import hashlib;id2=hashlib.md5(id).hexdigest()\");在请求之前评估提供的Python代码(例如: \"import hashlib;id2=hashlib.md5(id).hexdigest()\")")

        # Optimization options
        optimization = parser.add_argument_group("Optimization", "These options can be used to optimize the performance of sqlmap;这些选项可以用于优化sqlmap的性能")

        optimization.add_argument("-o", dest="optimize", action="store_true",
            help="Turn on all optimization switches;打开所有优化开关")

        optimization.add_argument("--predict-output", dest="predictOutput", action="store_true",
            help="Predict common queries output;预测常见查询输出")

        optimization.add_argument("--keep-alive", dest="keepAlive", action="store_true",
            help="Use persistent HTTP(s) connections;使用持久HTTP(s)连接")

        optimization.add_argument("--null-connection", dest="nullConnection", action="store_true",
            help="Retrieve page length without actual HTTP response body;在不实际HTTP响应体的情况下检索页面长度")

        optimization.add_argument("--threads", dest="threads", type=int,
            help="Max number of concurrent HTTP(s) requests (default %d);最大并发HTTP(s)请求数(默认%d)" % (defaults.threads, defaults.threads))

        # Injection options
        injection = parser.add_argument_group("Injection", "These options can be used to specify which parameters to test for, provide custom injection payloads and optional tampering scripts;这些选项可以用于指定要测试的参数，提供自定义注入有效负载和可选的篡改脚本")

        injection.add_argument("-p", dest="testParameter",
            help="Testable parameter(s);可测试参数(s)")

        injection.add_argument("--skip", dest="skip",
            help="Skip testing for given parameter(s);跳过给定参数的测试")

        injection.add_argument("--skip-static", dest="skipStatic", action="store_true",
            help="Skip testing parameters that not appear to be dynamic;跳过测试那些看起来不是动态的参数")

        injection.add_argument("--param-exclude", dest="paramExclude",
            help="Regexp to exclude parameters from testing (e.g. \"ses\");正则表达式排除参数测试(例如: \"ses\")")

        injection.add_argument("--param-filter", dest="paramFilter",
            help="Select testable parameter(s) by place (e.g. \"POST\");按位置选择可测试参数(例如: \"POST\")")

        injection.add_argument("--dbms", dest="dbms",
            help="Force back-end DBMS to provided value;强制后端DBMS为提供的值")

        injection.add_argument("--dbms-cred", dest="dbmsCred",
            help="DBMS authentication credentials (user:password);DBMS认证凭证(用户名:密码)")

        injection.add_argument("--os", dest="os",
            help="Force back-end DBMS operating system to provided value;强制后端DBMS操作系统为提供的值")

        injection.add_argument("--invalid-bignum", dest="invalidBignum", action="store_true",
            help="Use big numbers for invalidating values;使用大数字来无效化值")

        injection.add_argument("--invalid-logical", dest="invalidLogical", action="store_true",
            help="Use logical operations for invalidating values;使用逻辑操作来无效化值")

        injection.add_argument("--invalid-string", dest="invalidString", action="store_true",
            help="Use random strings for invalidating values;使用随机字符串来无效化值")

        injection.add_argument("--no-cast", dest="noCast", action="store_true",
            help="Turn off payload casting mechanism;关闭有效负载转换机制")

        injection.add_argument("--no-escape", dest="noEscape", action="store_true",
            help="Turn off string escaping mechanism;关闭字符串转义机制")

        injection.add_argument("--prefix", dest="prefix",
            help="Injection payload prefix string;注入有效负载前缀字符串")

        injection.add_argument("--suffix", dest="suffix",
            help="Injection payload suffix string;注入有效负载后缀字符串")

        injection.add_argument("--tamper", dest="tamper",
            help="Use given script(s) for tampering injection data;使用给定的脚本(s)来篡改注入数据")

        # Detection options
        detection = parser.add_argument_group("Detection", "These options can be used to customize the detection phase;这些选项可以用于自定义检测阶段")

        detection.add_argument("--level", dest="level", type=int,
            help="Level of tests to perform (1-5, default %d);测试级别(1-5, 默认%d)" % (defaults.level, defaults.level))

        detection.add_argument("--risk", dest="risk", type=int,
            help="Risk of tests to perform (1-3, default %d);测试风险(1-3, 默认%d)" % (defaults.risk, defaults.risk))

        detection.add_argument("--string", dest="string",
            help="String to match when query is evaluated to True;当查询评估为True时匹配的字符串")

        detection.add_argument("--not-string", dest="notString",
            help="String to match when query is evaluated to False;当查询评估为False时匹配的字符串")

        detection.add_argument("--regexp", dest="regexp",
            help="Regexp to match when query is evaluated to True;当查询评估为True时匹配的正则表达式")

        detection.add_argument("--code", dest="code", type=int,
            help="HTTP code to match when query is evaluated to True;当查询评估为True时匹配的HTTP代码")

        detection.add_argument("--smart", dest="smart", action="store_true",
            help="Perform thorough tests only if positive heuristic(s);仅在正向启发式(s)为真时执行彻底测试")

        detection.add_argument("--text-only", dest="textOnly", action="store_true",
            help="Compare pages based only on the textual content;仅基于文本内容比较页面")

        detection.add_argument("--titles", dest="titles", action="store_true",
            help="Compare pages based only on their titles;仅基于标题比较页面")

        # Techniques options
        techniques = parser.add_argument_group("Techniques", "These options can be used to tweak testing of specific SQL injection techniques;这些选项可以用于调整特定SQL注入技术的测试")

        techniques.add_argument("--technique", dest="technique",
            help="SQL injection techniques to use (default \"%s\");使用的SQL注入技术(默认\"%s\")" % (defaults.technique, defaults.technique))

        techniques.add_argument("--time-sec", dest="timeSec", type=int,
            help="Seconds to delay the DBMS response (default %d);延迟DBMS响应的秒数(默认%d)" % (defaults.timeSec, defaults.timeSec))

        techniques.add_argument("--disable-stats", dest="disableStats", action="store_true",
            help="Disable the statistical model for detecting the delay;禁用用于检测延迟的统计模型")

        techniques.add_argument("--union-cols", dest="uCols",
            help="Range of columns to test for UNION query SQL injection;测试UNION查询SQL注入的列范围")

        techniques.add_argument("--union-char", dest="uChar",
            help="Character to use for bruteforcing number of columns;用于蛮力猜测列数的字符")

        techniques.add_argument("--union-from", dest="uFrom",
            help="Table to use in FROM part of UNION query SQL injection;在UNION查询SQL注入的FROM部分使用的表")

        techniques.add_argument("--union-values", dest="uValues",
            help="Column values to use for UNION query SQL injection;用于UNION查询SQL注入的列值")

        techniques.add_argument("--dns-domain", dest="dnsDomain",
            help="Domain name used for DNS exfiltration attack;用于DNS外泄攻击的域名")

        techniques.add_argument("--second-url", dest="secondUrl",
            help="Resulting page URL searched for second-order response;用于第二级响应的页面URL")

        techniques.add_argument("--second-req", dest="secondReq",
            help="Load second-order HTTP request from file;从文件加载第二级HTTP请求")

        # Fingerprint options
        fingerprint = parser.add_argument_group("Fingerprint")

        fingerprint.add_argument("-f", "--fingerprint", dest="extensiveFp", action="store_true",
            help="Perform an extensive DBMS version fingerprint;执行广泛的DBMS版本指纹")

        # Enumeration options
        enumeration = parser.add_argument_group("Enumeration", "These options can be used to enumerate the back-end database management system information, structure and data contained in the tables;这些选项可以用于枚举后端数据库管理系统信息、结构和表中包含的数据")

        enumeration.add_argument("-a", "--all", dest="getAll", action="store_true",
            help="Retrieve everything;检索所有内容")

        enumeration.add_argument("-b", "--banner", dest="getBanner", action="store_true",
            help="Retrieve DBMS banner;检索DBMS横幅")

        enumeration.add_argument("--current-user", dest="getCurrentUser", action="store_true",
            help="Retrieve DBMS current user;检索DBMS当前用户")

        enumeration.add_argument("--current-db", dest="getCurrentDb", action="store_true",
            help="Retrieve DBMS current database;检索DBMS当前数据库")

        enumeration.add_argument("--hostname", dest="getHostname", action="store_true",
            help="Retrieve DBMS server hostname;检索DBMS服务器主机名")

        enumeration.add_argument("--is-dba", dest="isDba", action="store_true",
            help="Detect if the DBMS current user is DBA;检测DBMS当前用户是否为DBA")

        enumeration.add_argument("--users", dest="getUsers", action="store_true",
            help="Enumerate DBMS users;枚举DBMS用户")

        enumeration.add_argument("--passwords", dest="getPasswordHashes", action="store_true",
            help="Enumerate DBMS users password hashes;枚举DBMS用户密码哈希")

        enumeration.add_argument("--privileges", dest="getPrivileges", action="store_true",
            help="Enumerate DBMS users privileges;枚举DBMS用户权限")

        enumeration.add_argument("--roles", dest="getRoles", action="store_true",
            help="Enumerate DBMS users roles;枚举DBMS用户角色")

        enumeration.add_argument("--dbs", dest="getDbs", action="store_true",
            help="Enumerate DBMS databases;枚举DBMS数据库")

        enumeration.add_argument("--tables", dest="getTables", action="store_true",
            help="Enumerate DBMS database tables;枚举DBMS数据库表")

        enumeration.add_argument("--columns", dest="getColumns", action="store_true",
            help="Enumerate DBMS database table columns;枚举DBMS数据库表列")

        enumeration.add_argument("--schema", dest="getSchema", action="store_true",
            help="Enumerate DBMS schema;枚举DBMS模式")

        enumeration.add_argument("--count", dest="getCount", action="store_true",
            help="Retrieve number of entries for table(s);检索表(s)的条目数")

        enumeration.add_argument("--dump", dest="dumpTable", action="store_true",
            help="Dump DBMS database table entries;转储DBMS数据库表条目")

        enumeration.add_argument("--dump-all", dest="dumpAll", action="store_true",
            help="Dump all DBMS databases tables entries;转储所有DBMS数据库表条目")

        enumeration.add_argument("--search", dest="search", action="store_true",
            help="Search column(s), table(s) and/or database name(s);搜索列(s)、表(s)和/或数据库名称(s)")

        enumeration.add_argument("--comments", dest="getComments", action="store_true",
            help="Check for DBMS comments during enumeration;在枚举期间检查DBMS注释")

        enumeration.add_argument("--statements", dest="getStatements", action="store_true",
            help="Retrieve SQL statements being run on DBMS;检索DBMS上运行的SQL语句")

        enumeration.add_argument("-D", dest="db",
            help="DBMS database to enumerate;枚举DBMS数据库")

        enumeration.add_argument("-T", dest="tbl",
            help="DBMS database table(s) to enumerate;枚举DBMS数据库表(s)")

        enumeration.add_argument("-C", dest="col",
            help="DBMS database table column(s) to enumerate;枚举DBMS数据库表列(s)")

        enumeration.add_argument("-X", dest="exclude",
            help="DBMS database identifier(s) to not enumerate;不枚举DBMS数据库标识符(s)")

        enumeration.add_argument("-U", dest="user",
            help="DBMS user to enumerate;枚举DBMS用户")

        enumeration.add_argument("--exclude-sysdbs", dest="excludeSysDbs", action="store_true",
            help="Exclude DBMS system databases when enumerating tables;在枚举表时排除DBMS系统数据库")

        enumeration.add_argument("--pivot-column", dest="pivotColumn",
            help="Pivot column name;枢轴列名称")

        enumeration.add_argument("--where", dest="dumpWhere",
            help="Use WHERE condition while table dumping;在转储表时使用WHERE条件")

        enumeration.add_argument("--start", dest="limitStart", type=int,
            help="First dump table entry to retrieve;第一个转储表条目")

        enumeration.add_argument("--stop", dest="limitStop", type=int,
            help="Last dump table entry to retrieve;最后一个转储表条目")

        enumeration.add_argument("--first", dest="firstChar", type=int,
            help="First query output word character to retrieve;第一个查询输出单词字符")

        enumeration.add_argument("--last", dest="lastChar", type=int,
            help="Last query output word character to retrieve;最后一个查询输出单词字符")

        enumeration.add_argument("--sql-query", dest="sqlQuery",
            help="SQL statement to be executed;要执行的SQL语句")

        enumeration.add_argument("--sql-shell", dest="sqlShell", action="store_true",
            help="Prompt for an interactive SQL shell;提示交互式SQL shell")

        enumeration.add_argument("--sql-file", dest="sqlFile",
            help="Execute SQL statements from given file(s);从给定文件(s)执行SQL语句")

        # Brute force options
        brute = parser.add_argument_group("Brute force", "These options can be used to run brute force checks;这些选项可以用于运行暴力破解检查")

        brute.add_argument("--common-tables", dest="commonTables", action="store_true",
            help="Check existence of common tables;检查常见表的存在")

        brute.add_argument("--common-columns", dest="commonColumns", action="store_true",
            help="Check existence of common columns;检查常见列的存在")

        brute.add_argument("--common-files", dest="commonFiles", action="store_true",
            help="Check existence of common files;检查常见文件的存在")

        # User-defined function options
        udf = parser.add_argument_group("User-defined function injection", "These options can be used to create custom user-defined functions;这些选项可以用于创建自定义用户定义函数")

        udf.add_argument("--udf-inject", dest="udfInject", action="store_true",
            help="Inject custom user-defined functions;注入自定义用户定义函数")

        udf.add_argument("--shared-lib", dest="shLib",
            help="Local path of the shared library;共享库的本地路径")

        # File system options
        filesystem = parser.add_argument_group("File system access", "These options can be used to access the back-end database management system underlying file system;这些选项可以用于访问后端数据库管理系统的底层文件系统")

        filesystem.add_argument("--file-read", dest="fileRead",
            help="Read a file from the back-end DBMS file system;从后端DBMS文件系统读取文件")

        filesystem.add_argument("--file-write", dest="fileWrite",
            help="Write a local file on the back-end DBMS file system;将本地文件写入后端DBMS文件系统")

        filesystem.add_argument("--file-dest", dest="fileDest",
            help="Back-end DBMS absolute filepath to write to;要写入的后端DBMS绝对文件路径")

        # Takeover options
        takeover = parser.add_argument_group("Operating system access", "These options can be used to access the back-end database management system underlying operating system;这些选项可以用于访问后端数据库管理系统的底层操作系统")

        takeover.add_argument("--os-cmd", dest="osCmd",
            help="Execute an operating system command;执行操作系统命令")

        takeover.add_argument("--os-shell", dest="osShell", action="store_true",
            help="Prompt for an interactive operating system shell;提示交互式操作系统shell")

        takeover.add_argument("--os-pwn", dest="osPwn", action="store_true",
            help="Prompt for an OOB shell, Meterpreter or VNC;提示OOB shell、Meterpreter或VNC")

        takeover.add_argument("--os-smbrelay", dest="osSmb", action="store_true",
            help="One click prompt for an OOB shell, Meterpreter or VNC;一键提示OOB shell、Meterpreter或VNC")

        takeover.add_argument("--os-bof", dest="osBof", action="store_true",
            help="Stored procedure buffer overflow exploitation;存储过程缓冲区溢出利用")

        takeover.add_argument("--priv-esc", dest="privEsc", action="store_true",
            help="Database process user privilege escalation;数据库进程用户特权提升")

        takeover.add_argument("--msf-path", dest="msfPath",
            help="Local path where Metasploit Framework is installed;Metasploit Framework安装的本地路径")

        takeover.add_argument("--tmp-path", dest="tmpPath",
            help="Remote absolute path of temporary files directory;远程绝对路径的临时文件目录")

        # Windows registry options
        windows = parser.add_argument_group("Windows registry access", "These options can be used to access the back-end database management system Windows registry;这些选项可以用于访问后端数据库管理系统的Windows注册表")

        windows.add_argument("--reg-read", dest="regRead", action="store_true",
            help="Read a Windows registry key value;读取Windows注册表键值")

        windows.add_argument("--reg-add", dest="regAdd", action="store_true",
            help="Write a Windows registry key value data;写入Windows注册表键值数据")

        windows.add_argument("--reg-del", dest="regDel", action="store_true",
            help="Delete a Windows registry key value;删除Windows注册表键值")

        windows.add_argument("--reg-key", dest="regKey",
            help="Windows registry key;Windows注册表键")

        windows.add_argument("--reg-value", dest="regVal",
            help="Windows registry key value;Windows注册表键值")

        windows.add_argument("--reg-data", dest="regData",
            help="Windows registry key value data;Windows注册表键值数据")

        windows.add_argument("--reg-type", dest="regType",
            help="Windows registry key value type;Windows注册表键值类型")

        # General options
        general = parser.add_argument_group("General", "These options can be used to set some general working parameters;这些选项可以用于设置一些一般的工作参数")

        general.add_argument("-s", dest="sessionFile",
            help="Load session from a stored (.sqlite) file;从存储的(.sqlite)文件加载会话")

        general.add_argument("-t", dest="trafficFile",
            help="Log all HTTP traffic into a textual file;将所有HTTP流量记录到文本文件中")

        general.add_argument("--abort-on-empty", dest="abortOnEmpty", action="store_true",
            help="Abort data retrieval on empty results;在空结果时中止数据获取")

        general.add_argument("--answers", dest="answers",
            help="Set predefined answers (e.g. \"quit=N,follow=N\");设置预定义答案(例如\"quit=N,follow=N\")")

        general.add_argument("--base64", dest="base64Parameter",
            help="Parameter(s) containing Base64 encoded data;包含Base64编码数据的参数(s)")

        general.add_argument("--base64-safe", dest="base64Safe", action="store_true",
            help="Use URL and filename safe Base64 alphabet (RFC 4648);使用URL和文件名安全的Base64字母表(RFC 4648)")

        general.add_argument("--batch", dest="batch", action="store_true",
            help="Never ask for user input, use the default behavior;从不询问用户输入，使用默认行为")

        general.add_argument("--binary-fields", dest="binaryFields",
            help="Result fields having binary values (e.g. \"digest\");具有二进制值的结果字段(例如\"digest\")")

        general.add_argument("--check-internet", dest="checkInternet", action="store_true",
            help="Check Internet connection before assessing the target;在评估目标之前检查Internet连接")

        general.add_argument("--cleanup", dest="cleanup", action="store_true",
            help="Clean up the DBMS from sqlmap specific UDF and tables;清理DBMS中的sqlmap特定UDF和表")

        general.add_argument("--crawl", dest="crawlDepth", type=int,
            help="Crawl the website starting from the target URL;从目标URL开始爬取网站")

        general.add_argument("--crawl-exclude", dest="crawlExclude",
            help="Regexp to exclude pages from crawling (e.g. \"logout\");从爬取中排除页面(例如\"logout\")")

        general.add_argument("--csv-del", dest="csvDel",
            help="Delimiting character used in CSV output (default \"%s\");CSV输出中使用的分隔符(默认\"%s\"))" % (defaults.csvDel,defaults.csvDel))

        general.add_argument("--charset", dest="charset",
            help="Blind SQL injection charset (e.g. \"0123456789abcdef\");盲SQL注入字符集(例如\"0123456789abcdef\")")

        general.add_argument("--dump-file", dest="dumpFile",
            help="Store dumped data to a custom file;将转储数据存储到自定义文件中")

        general.add_argument("--dump-format", dest="dumpFormat",
            help="Format of dumped data (CSV (default), HTML or SQLITE);转储数据的格式(CSV(默认)、HTML或SQLITE)")

        general.add_argument("--encoding", dest="encoding",
            help="Character encoding used for data retrieval (e.g. GBK);用于数据检索的字符编码(例如GBK)")

        general.add_argument("--eta", dest="eta", action="store_true",
            help="Display for each output the estimated time of arrival;显示每个输出的预计到达时间")

        general.add_argument("--flush-session", dest="flushSession", action="store_true",
            help="Flush session files for current target;刷新当前目标的会话文件")

        general.add_argument("--forms", dest="forms", action="store_true",
            help="Parse and test forms on target URL;解析和测试目标URL上的表单")

        general.add_argument("--fresh-queries", dest="freshQueries", action="store_true",
            help="Ignore query results stored in session file;忽略会话文件中存储的查询结果")

        general.add_argument("--gpage", dest="googlePage", type=int,
            help="Use Google dork results from specified page number;使用指定页面的Google dork结果")

        general.add_argument("--har", dest="harFile",
            help="Log all HTTP traffic into a HAR file;将所有HTTP流量记录到HAR文件中")

        general.add_argument("--hex", dest="hexConvert", action="store_true",
            help="Use hex conversion during data retrieval;在数据检索期间使用十六进制转换")

        general.add_argument("--output-dir", dest="outputDir", action="store",
            help="Custom output directory path;自定义输出目录路径")

        general.add_argument("--parse-errors", dest="parseErrors", action="store_true",
            help="Parse and display DBMS error messages from responses;解析和显示DBMS错误消息")

        general.add_argument("--preprocess", dest="preprocess",
            help="Use given script(s) for preprocessing (request);使用给定的脚本(s)进行预处理(请求)")

        general.add_argument("--postprocess", dest="postprocess",
            help="Use given script(s) for postprocessing (response);使用给定的脚本(s)进行后处理(响应)")

        general.add_argument("--repair", dest="repair", action="store_true",
            help="Redump entries having unknown character marker (%s);重新转储具有未知字符标记的条目(%s)" % (INFERENCE_UNKNOWN_CHAR,INFERENCE_UNKNOWN_CHAR))

        general.add_argument("--save", dest="saveConfig",
            help="Save options to a configuration INI file;将选项保存到配置INI文件中")

        general.add_argument("--scope", dest="scope",
            help="Regexp for filtering targets;正则表达式用于过滤目标")

        general.add_argument("--skip-heuristics", dest="skipHeuristics", action="store_true",
            help="Skip heuristic detection of vulnerabilities;跳过漏洞的启发式检测")

        general.add_argument("--skip-waf", dest="skipWaf", action="store_true",
            help="Skip heuristic detection of WAF/IPS protection;跳过WAF/IPS保护的启发式检测")

        general.add_argument("--table-prefix", dest="tablePrefix",
            help="Prefix used for temporary tables (default: \"%s\")" % defaults.tablePrefix)

        general.add_argument("--test-filter", dest="testFilter",
            help="Select tests by payloads and/or titles (e.g. ROW);根据有效载荷和/或标题选择测试(例如ROW)")

        general.add_argument("--test-skip", dest="testSkip",
            help="Skip tests by payloads and/or titles (e.g. BENCHMARK);根据有效载荷和/或标题跳过测试(例如BENCHMARK)")

        general.add_argument("--time-limit", dest="timeLimit", type=float,
            help="Run with a time limit in seconds (e.g. 3600);以秒为单位运行，时间限制(例如3600)")

        general.add_argument("--unsafe-naming", dest="unsafeNaming", action="store_true",
            help="Disable escaping of DBMS identifiers (e.g. \"user\");禁用DBMS标识符的转义(例如\"user\")")

        general.add_argument("--web-root", dest="webRoot",
            help="Web server document root directory (e.g. \"/var/www\");Web服务器文档根目录(例如\"/var/www\")")

        # Miscellaneous options
        miscellaneous = parser.add_argument_group("Miscellaneous", "These options do not fit into any other category;这些选项不适合任何其他类别")

        miscellaneous.add_argument("-z", dest="mnemonics",
            help="Use short mnemonics (e.g. \"flu,bat,ban,tec=EU\");使用短助记符(例如\"flu,bat,ban,tec=EU\")")

        miscellaneous.add_argument("--alert", dest="alert",
            help="Run host OS command(s) when SQL injection is found;当SQL注入被发现时运行主机OS命令(s)")

        miscellaneous.add_argument("--beep", dest="beep", action="store_true",
            help="Beep on question and/or when vulnerability is found;当问题或漏洞被发现时发出蜂鸣声")

        miscellaneous.add_argument("--dependencies", dest="dependencies", action="store_true",
            help="Check for missing (optional) sqlmap dependencies;检查缺失的(可选)sqlmap依赖项")

        miscellaneous.add_argument("--disable-coloring", dest="disableColoring", action="store_true",
            help="Disable console output coloring;禁用控制台输出着色")

        miscellaneous.add_argument("--disable-hashing", dest="disableHashing", action="store_true",
            help="Disable hash analysis on table dumps;禁用表转储上的哈希分析")

        miscellaneous.add_argument("--list-tampers", dest="listTampers", action="store_true",
            help="Display list of available tamper scripts;显示可用的tamper脚本列表")

        miscellaneous.add_argument("--no-logging", dest="noLogging", action="store_true",
            help="Disable logging to a file;禁用日志记录到文件")

        miscellaneous.add_argument("--no-truncate", dest="noTruncate", action="store_true",
            help="Disable console output truncation (e.g. long entr...);禁用控制台输出截断(例如长条目...)")

        miscellaneous.add_argument("--offline", dest="offline", action="store_true",
            help="Work in offline mode (only use session data);以离线模式工作(仅使用会话数据)")

        miscellaneous.add_argument("--purge", dest="purge", action="store_true",
            help="Safely remove all content from sqlmap data directory;安全地从sqlmap数据目录中删除所有内容")

        miscellaneous.add_argument("--results-file", dest="resultsFile",
            help="Location of CSV results file in multiple targets mode;多个目标模式中CSV结果文件的位置")

        miscellaneous.add_argument("--shell", dest="shell", action="store_true",
            help="Prompt for an interactive sqlmap shell;提示交互式sqlmap shell")

        miscellaneous.add_argument("--tmp-dir", dest="tmpDir",
            help="Local directory for storing temporary files;临时文件存储的本地目录")

        miscellaneous.add_argument("--unstable", dest="unstable", action="store_true",
            help="Adjust options for unstable connections;调整不稳定连接的选项")

        miscellaneous.add_argument("--update", dest="updateAll", action="store_true",
            help="Update sqlmap;更新sqlmap")

        miscellaneous.add_argument("--wizard", dest="wizard", action="store_true",
            help="Simple wizard interface for beginner users;简单的向导界面")

        # Hidden and/or experimental options
        parser.add_argument("--crack", dest="hashFile",
            help=SUPPRESS)  # "Load and crack hashes from a file (standalone)"

        parser.add_argument("--dummy", dest="dummy", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--yuge", dest="yuge", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--murphy-rate", dest="murphyRate", type=int,
            help=SUPPRESS)

        parser.add_argument("--debug", dest="debug", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--deprecations", dest="deprecations", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--disable-multi", dest="disableMulti", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--disable-precon", dest="disablePrecon", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--profile", dest="profile", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--localhost", dest="localhost", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--force-dbms", dest="forceDbms",
            help=SUPPRESS)

        parser.add_argument("--force-dns", dest="forceDns", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--force-partial", dest="forcePartial", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--force-pivoting", dest="forcePivoting", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--ignore-stdin", dest="ignoreStdin", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--non-interactive", dest="nonInteractive", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--gui", dest="gui", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--smoke-test", dest="smokeTest", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--vuln-test", dest="vulnTest", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--disable-json", dest="disableJson", action="store_true",
            help=SUPPRESS)

        # API options
        parser.add_argument("--api", dest="api", action="store_true",
            help=SUPPRESS)

        parser.add_argument("--taskid", dest="taskid",
            help=SUPPRESS)

        parser.add_argument("--database", dest="database",
            help=SUPPRESS)

        # Dirty hack to display longer options without breaking into two lines
        if hasattr(parser, "formatter"):
            def _(self, *args):
                retVal = parser.formatter._format_option_strings(*args)
                if len(retVal) > MAX_HELP_OPTION_LENGTH:
                    retVal = ("%%.%ds.." % (MAX_HELP_OPTION_LENGTH - parser.formatter.indent_increment)) % retVal
                return retVal

            parser.formatter._format_option_strings = parser.formatter.format_option_strings
            parser.formatter.format_option_strings = type(parser.formatter.format_option_strings)(_, parser)
        else:
            def _format_action_invocation(self, action):
                retVal = self.__format_action_invocation(action)
                if len(retVal) > MAX_HELP_OPTION_LENGTH:
                    retVal = ("%%.%ds.." % (MAX_HELP_OPTION_LENGTH - self._indent_increment)) % retVal
                return retVal

            parser.formatter_class.__format_action_invocation = parser.formatter_class._format_action_invocation
            parser.formatter_class._format_action_invocation = _format_action_invocation

        # Dirty hack for making a short option '-hh'
        if hasattr(parser, "get_option"):
            option = parser.get_option("--hh")
            option._short_opts = ["-hh"]
            option._long_opts = []
        else:
            for action in get_actions(parser):
                if action.option_strings == ["--hh"]:
                    action.option_strings = ["-hh"]
                    break

        # Dirty hack for inherent help message of switch '-h'
        if hasattr(parser, "get_option"):
            option = parser.get_option("-h")
            option.help = option.help.capitalize().replace("this help", "basic help")
        else:
            for action in get_actions(parser):
                if action.option_strings == ["-h", "--help"]:
                    action.help = action.help.capitalize().replace("this help", "basic help")
                    break

        _ = []
        advancedHelp = True
        extraHeaders = []
        auxIndexes = {}

        # Reference: https://stackoverflow.com/a/4012683 (Note: previously used "...sys.getfilesystemencoding() or UNICODE_ENCODING")
        for arg in argv:
            _.append(getUnicode(arg, encoding=sys.stdin.encoding))

        argv = _
        checkOldOptions(argv)

        if "--gui" in argv:
            from lib.core.gui import runGui

            runGui(parser)

            raise SqlmapSilentQuitException

        elif "--shell" in argv:
            _createHomeDirectories()

            parser.usage = ""
            cmdLineOptions.sqlmapShell = True

            commands = set(("x", "q", "exit", "quit", "clear"))
            commands.update(get_all_options(parser))

            autoCompletion(AUTOCOMPLETE_TYPE.SQLMAP, commands=commands)

            while True:
                command = None
                prompt = "sqlmap > "

                try:
                    # Note: in Python2 command should not be converted to Unicode before passing to shlex (Reference: https://bugs.python.org/issue1170)
                    command = _input(prompt).strip()
                except (KeyboardInterrupt, EOFError):
                    print()
                    raise SqlmapShellQuitException

                command = re.sub(r"(?i)\Anew\s+", "", command or "")

                if not command:
                    continue
                elif command.lower() == "clear":
                    clearHistory()
                    dataToStdout("[i] history cleared\n")
                    saveHistory(AUTOCOMPLETE_TYPE.SQLMAP)
                elif command.lower() in ("x", "q", "exit", "quit"):
                    raise SqlmapShellQuitException
                elif command[0] != '-':
                    if not re.search(r"(?i)\A(\?|help)\Z", command):
                        dataToStdout("[!] invalid option(s) provided\n")
                    dataToStdout("[i] valid example: '-u http://www.site.com/vuln.php?id=1 --banner'\n")
                else:
                    saveHistory(AUTOCOMPLETE_TYPE.SQLMAP)
                    loadHistory(AUTOCOMPLETE_TYPE.SQLMAP)
                    break

            try:
                for arg in shlex.split(command):
                    argv.append(getUnicode(arg, encoding=sys.stdin.encoding))
            except ValueError as ex:
                raise SqlmapSyntaxException("something went wrong during command line parsing ('%s')" % getSafeExString(ex))

        longOptions = set(re.findall(r"\-\-([^= ]+?)=", parser.format_help()))
        longSwitches = set(re.findall(r"\-\-([^= ]+?)\s", parser.format_help()))

        for i in xrange(len(argv)):
            # Reference: https://en.wiktionary.org/wiki/-
            argv[i] = re.sub(u"\\A(\u2010|\u2013|\u2212|\u2014|\u4e00|\u1680|\uFE63|\uFF0D)+", lambda match: '-' * len(match.group(0)), argv[i])

            # Reference: https://unicode-table.com/en/sets/quotation-marks/
            argv[i] = argv[i].strip(u"\u00AB\u2039\u00BB\u203A\u201E\u201C\u201F\u201D\u2019\u275D\u275E\u276E\u276F\u2E42\u301D\u301E\u301F\uFF02\u201A\u2018\u201B\u275B\u275C")

            if argv[i] == "-hh":
                argv[i] = "-h"
            elif i == 1 and re.search(r"\A(http|www\.|\w[\w.-]+\.\w{2,})", argv[i]) is not None:
                argv[i] = "--url=%s" % argv[i]
            elif len(argv[i]) > 1 and all(ord(_) in xrange(0x2018, 0x2020) for _ in ((argv[i].split('=', 1)[-1].strip() or ' ')[0], argv[i][-1])):
                dataToStdout("[!] copy-pasting illegal (non-console) quote characters from Internet is illegal (%s)\n" % argv[i])
                raise SystemExit
            elif len(argv[i]) > 1 and u"\uff0c" in argv[i].split('=', 1)[-1]:
                dataToStdout("[!] copy-pasting illegal (non-console) comma characters from Internet is illegal (%s)\n" % argv[i])
                raise SystemExit
            elif re.search(r"\A-\w=.+", argv[i]):
                dataToStdout("[!] potentially miswritten (illegal '=') short option detected ('%s')\n" % argv[i])
                raise SystemExit
            elif re.search(r"\A-\w{3,}", argv[i]):
                if argv[i].strip('-').split('=')[0] in (longOptions | longSwitches):
                    argv[i] = "-%s" % argv[i]
            elif argv[i] in IGNORED_OPTIONS:
                argv[i] = ""
            elif argv[i] in DEPRECATED_OPTIONS:
                argv[i] = ""
            elif argv[i] in ("-s", "--silent"):
                if i + 1 < len(argv) and argv[i + 1].startswith('-') or i + 1 == len(argv):
                    argv[i] = ""
                    conf.verbose = 0
            elif argv[i].startswith("--data-raw"):
                argv[i] = argv[i].replace("--data-raw", "--data", 1)
            elif argv[i].startswith("--auth-creds"):
                argv[i] = argv[i].replace("--auth-creds", "--auth-cred", 1)
            elif argv[i].startswith("--drop-cookie"):
                argv[i] = argv[i].replace("--drop-cookie", "--drop-set-cookie", 1)
            elif re.search(r"\A--tamper[^=\s]", argv[i]):
                argv[i] = ""
            elif re.search(r"\A(--(tamper|ignore-code|skip))(?!-)", argv[i]):
                key = re.search(r"\-?\-(\w+)\b", argv[i]).group(1)
                index = auxIndexes.get(key, None)
                if index is None:
                    index = i if '=' in argv[i] else (i + 1 if i + 1 < len(argv) and not argv[i + 1].startswith('-') else None)
                    auxIndexes[key] = index
                else:
                    delimiter = ','
                    argv[index] = "%s%s%s" % (argv[index], delimiter, argv[i].split('=')[1] if '=' in argv[i] else (argv[i + 1] if i + 1 < len(argv) and not argv[i + 1].startswith('-') else ""))
                    argv[i] = ""
            elif argv[i] in ("-H", "--header") or any(argv[i].startswith("%s=" % _) for _ in ("-H", "--header")):
                if '=' in argv[i]:
                    extraHeaders.append(argv[i].split('=', 1)[1])
                elif i + 1 < len(argv):
                    extraHeaders.append(argv[i + 1])
            elif argv[i] == "--deps":
                argv[i] = "--dependencies"
            elif argv[i] == "--disable-colouring":
                argv[i] = "--disable-coloring"
            elif argv[i] == "-r":
                for j in xrange(i + 2, len(argv)):
                    value = argv[j]
                    if os.path.isfile(value):
                        argv[i + 1] += ",%s" % value
                        argv[j] = ''
                    else:
                        break
            elif re.match(r"\A\d+!\Z", argv[i]) and argv[max(0, i - 1)] == "--threads" or re.match(r"\A--threads.+\d+!\Z", argv[i]):
                argv[i] = argv[i][:-1]
                conf.skipThreadCheck = True
            elif argv[i] == "--version":
                print(VERSION_STRING.split('/')[-1])
                raise SystemExit
            elif argv[i] in ("-h", "--help"):
                advancedHelp = False
                for group in get_groups(parser)[:]:
                    found = False
                    for option in get_actions(group):
                        if option.dest not in BASIC_HELP_ITEMS:
                            option.help = SUPPRESS
                        else:
                            found = True
                    if not found:
                        get_groups(parser).remove(group)
            elif '=' in argv[i] and not argv[i].startswith('-') and argv[i].split('=')[0] in longOptions and re.search(r"\A-{1,2}\w", argv[i - 1]) is None:
                dataToStdout("[!] detected usage of long-option without a starting hyphen ('%s')\n" % argv[i])
                raise SystemExit

        for verbosity in (_ for _ in argv if re.search(r"\A\-v+\Z", _)):
            try:
                if argv.index(verbosity) == len(argv) - 1 or not argv[argv.index(verbosity) + 1].isdigit():
                    conf.verbose = verbosity.count('v')
                    del argv[argv.index(verbosity)]
            except (IndexError, ValueError):
                pass

        try:
            (args, _) = parser.parse_known_args(argv) if hasattr(parser, "parse_known_args") else parser.parse_args(argv)
        except UnicodeEncodeError as ex:
            dataToStdout("\n[!] %s\n" % getUnicode(ex.object.encode("unicode-escape")))
            raise SystemExit
        except SystemExit:
            if "-h" in argv and not advancedHelp:
                dataToStdout("\n[!] to see full list of options run with '-hh'\n")
            raise

        if extraHeaders:
            if not args.headers:
                args.headers = ""
            delimiter = "\\n" if "\\n" in args.headers else "\n"
            args.headers += delimiter + delimiter.join(extraHeaders)

        # Expand given mnemonic options (e.g. -z "ign,flu,bat")
        for i in xrange(len(argv) - 1):
            if argv[i] == "-z":
                expandMnemonics(argv[i + 1], parser, args)

        if args.dummy:
            args.url = args.url or DUMMY_URL

        if hasattr(sys.stdin, "fileno") and not any((os.isatty(sys.stdin.fileno()), args.api, args.ignoreStdin, "GITHUB_ACTIONS" in os.environ)):
            args.stdinPipe = iter(sys.stdin.readline, None)
        else:
            args.stdinPipe = None

        if not any((args.direct, args.url, args.logFile, args.bulkFile, args.googleDork, args.configFile, args.requestFile, args.updateAll, args.smokeTest, args.vulnTest, args.wizard, args.dependencies, args.purge, args.listTampers, args.hashFile, args.stdinPipe)):
            errMsg = "missing a mandatory option (-d, -u, -l, -m, -r, -g, -c, --wizard, --shell, --update, --purge, --list-tampers or --dependencies). "
            errMsg += "Use -h for basic and -hh for advanced help\n"
            parser.error(errMsg)

        return args

    except (ArgumentError, TypeError) as ex:
        parser.error(ex)

    except SystemExit:
        # Protection against Windows dummy double clicking
        if IS_WIN and "--non-interactive" not in sys.argv:
            dataToStdout("\nPress Enter to continue...")
            _input()
        raise

    debugMsg = "parsing command line"
    logger.debug(debugMsg)
