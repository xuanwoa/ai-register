import warnings

warnings.filterwarnings(
	"ignore",
	message=r"urllib3 v2 only supports OpenSSL 1\.1\.1\+.*",
	category=Warning,
	module=r"urllib3(\..*)?",
)

import urllib3
from urllib3.exceptions import NotOpenSSLWarning

warnings.filterwarnings("ignore", category=NotOpenSSLWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
