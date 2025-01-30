import pytest
import tarfile
import io


@pytest.fixture
def valid_csv_content():
    """
    Provides minimal valid CSV content for testing.
    Contains required fields: srcid, obs_id, and src_num.
    """
    return ("srcid,obs_id,src_num\n"
            "201237001010017,147510801,9")


@pytest.fixture
def invalid_csv_content():
    """
    Provides invalid CSV content missing required fields.
    Used for testing error handling of malformed input.
    """
    return "iauname,detid\n4XMM,123"


@pytest.fixture
def csv_path(tmp_path, valid_csv_content):
    """
    Creates a temporary CSV file with valid content.
    Returns the path to the temporary file.
    Dependencies:
        - tmp_path: pytest built-in fixture
        - valid_csv_content: fixture providing CSV content
    """
    path = tmp_path / "test_sources.csv"
    path.write_text(valid_csv_content)
    return path


@pytest.fixture
def invalid_csv_path(tmp_path, invalid_csv_content):
    """
    Creates a temporary CSV file with invalid content.
    Used for testing error handling of malformed CSV files.
    Dependencies:
        - tmp_path: pytest built-in fixture
        - invalid_csv_content: fixture providing invalid CSV content
    """
    path = tmp_path / "bad.csv"
    path.write_text(invalid_csv_content)
    return path


@pytest.fixture
def temp_dir_with_files(tmp_path):
    """
    Creates a temporary directory containing test files.
    Creates empty files with extensions: .FTZ, .PNG, .PDF
    Returns the path to the temporary directory.
    """
    for ext in ['.FTZ', '.PNG', '.PDF']:
        (tmp_path / f'test{ext}').touch()
    return tmp_path


@pytest.fixture
def mock_response(mocker):
    """
    Creates a mock HTTP response object.
    Simulates successful response with content-length and data.
    Used for testing download functionality without actual HTTP requests.
    """
    mock = mocker.Mock()
    mock.headers = {'content-length': '1024'}
    mock.iter_content.return_value = [b'data']
    return mock


@pytest.fixture
def mock_requests_get(mocker, mock_response):
    """
    Patches requests.get to return a mock response.
    Used to avoid actual HTTP requests during testing.
    Dependencies:
        - mocker: pytest-mock fixture
        - mock_response: fixture providing mock response object
    """
    return mocker.patch('requests.get', return_value=mock_response)


@pytest.fixture
def sample_tar_bytes():
    """Create sample tar with PPS files"""
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode='w:gz') as tar:
        # Create sample PPS file
        content = io.BytesIO(b'test data')
        info = tarfile.TarInfo('123456/pps/test.FTZ')
        info.size = len(content.getvalue())
        tar.addfile(info, content)
    return tar_buffer.getvalue()

@pytest.fixture
def mock_response(mocker, sample_tar_bytes):
    """Mock successful HTTP response"""
    mock = mocker.Mock()
    mock.headers = {'content-length': str(len(sample_tar_bytes))}
    mock.iter_content.return_value = [sample_tar_bytes]
    return mock

@pytest.fixture
def mock_requests_get(mocker, mock_response):
    """Mock requests.get"""
    return mocker.patch('requests.get', return_value=mock_response)