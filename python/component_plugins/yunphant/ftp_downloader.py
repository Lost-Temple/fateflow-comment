from fate_arch.common import log
from _base import (
    BaseParam,
    ComponentBase,
    ComponentMeta,
    ComponentInputProtocol,
)

LOGGER = log.getLogger()

ftp_downloader_cpn_meta = ComponentMeta("Ftp_Download")


# import pysftp
#
# def download_file():
#     cnopts = pysftp.CnOpts()
#     cnopts.hostkeys = None
#     with pysftp.Connection('hostname', username='username', password='password', cnopts=cnopts) as sftp:
#         remote_file_path = '/remote/path/to/file'
#         local_file_path = '/local/path/to/file'
#         sftp.get(remote_file_path, local_file_path, preserve_mtime=True)
#
# if __name__ == '__main__':
#     download_file()
# 在上面的代码中，断点续传的功能是通过添加参数preserve_mtime=True来实现的。这个参数会保留文件的修改时间，从而使得在断点续传时可以正确地计算出文件的偏移量。

@ftp_downloader_cpn_meta.bind_param
class DownloadParam(BaseParam):
    def __int__(
            self,
            hostname="",
            username="",
            password="",
            port=22,
            remote_file_path=""
    ):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.remote_file_path = remote_file_path
