"""This module provides functions for interacting with the Logfire "Explore" page.

The public functions in this module can be used both locally and in the Logfire "Explore" page,
and should behave similarly in both. This allows you to develop and test your code locally,
and then use it in the Logfire "Explore" page without changes.
"""
import sys
from functools import cache
from pathlib import Path
from typing import Any, Literal, TypedDict

_in_pyodide = 'pyodide' in sys.modules

try:
    import httpx
except ImportError:
    if _in_pyodide:
        # httpx should only be used outside pyodide
        # it cannot be used inside pyodide due to lack of sockets
        # pyodide provides pyodide.http.fetch to work around this
        httpx = None
    else:
        raise

try:
    _in_jupyter = get_ipython().__class__.__name__ == 'ZMQInteractiveShell'  # type: ignore
except NameError:
    _in_jupyter = False

_PYODIDE_NOT_ALLOWED_MESSAGE = 'This function should not be called in the logfire frontend.'
_PYODIDE_MUST_INJECT_MESSAGE = 'This function should be injected into pyodide by the web worker.'


def configure(
    token: str | None = None,
    data_dir: Path = Path('.logfire'),
    base_url: str | None = None,
) -> None:
    """This function sets the arguments used to obtain the Logfire token used in the `logfire.dash` module."""
    if _in_pyodide:
        # Ignore this call in pyodide, to make it easier to copy/paste code that works outside pyodide.
        return
        # Alternatively, we could raise an error:
        # raise RuntimeError(_PYODIDE_NOT_ALLOWED_MESSAGE)

    global _configured, _token, _data_dir, _base_url
    _token = token
    _data_dir = data_dir
    _base_url = base_url

    _get_token.cache_clear()

    _configured = True


async def query(sql: str) -> list[dict[str, Any]]:
    """Accepts a raw SQL query string, and executes it directly."""
    data = await _raw_query(sql)
    if data['status'] == 'success':
        return data['clickhouse_data']
    else:
        error_details = data['error_details']
        raise ValueError(f'Error running query:\n{error_details}')


class _Success(TypedDict):
    status: Literal['success']
    clickhouse_data: list[dict[str, Any]]


class _Error(TypedDict):
    status: Literal['error']
    error_details: str


async def _raw_query(q: str) -> _Success | _Error:
    """Accepts a raw query string, and returns the results as a list of dicts mapping column-name to value.

    This can be converted into a pandas `DataFrame` via `pd.DataFrame.from_records(results)`.
    """
    if _in_pyodide:
        raise RuntimeError(_PYODIDE_MUST_INJECT_MESSAGE)

    assert httpx is not None
    from ._constants import LOGFIRE_BASE_URL

    # Need to use a logfire configuration
    # Should we expose the token as part of the configuration
    token = _get_token()
    client = httpx.AsyncClient(headers={'Authorization': token})
    route = (_base_url or LOGFIRE_BASE_URL) + '/dash/query'
    response = await client.get(route, params={'q': q})
    response.raise_for_status()
    return response.json()


def show(item: Any) -> None:
    """Display the provided item in the UI appropriately.

    In a jupyter notebook, this will show the item under the cell as usual, and in the Logfire "Explore" page, this will
    show the item in the "Display" area. When called in a standard python script, this function behaves as `print`.
    """
    if _in_pyodide:
        raise RuntimeError(_PYODIDE_MUST_INJECT_MESSAGE)
    elif _in_jupyter:
        from IPython.display import display  # type: ignore

        display(item)
    else:
        print(item)


_configured: bool = False
_token: str | None = None
_data_dir: Path = Path('.logfire')
_base_url: str | None = None


@cache
def _get_token() -> str:
    if _in_pyodide:
        raise RuntimeError(_PYODIDE_NOT_ALLOWED_MESSAGE)

    if not _configured:
        configure()

    from ._config import LogfireConfig
    from .exceptions import LogfireConfigError

    token, _ = LogfireConfig.load_token(token=_token, data_dir=_data_dir)
    if token is None:
        raise LogfireConfigError(
            'No logfire token provided or found in the default locations.'
            ' You can set the token via the environment variable `LOGFIRE_TOKEN`,'
            ' or with a call to `logfire.dash.configure`.'
        )
    return token