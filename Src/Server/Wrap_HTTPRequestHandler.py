import logging
from http.server import BaseHTTPRequestHandler


class Wrap_HTTPRequestHandler(BaseHTTPRequestHandler):

    def log_error(self, format, *args):
        address_string = "SERVER"
        if self.client_address:
            address_string = self.client_address[0]
        logging.error("%s - %s\n" % (address_string, format % args))

    def log_message(self, format, *args):
        address_string = "SERVER"
        if self.client_address:
            address_string = self.client_address[0]
        logging.info("%s - %s\n" % (address_string, format % args))

    def end_headers(self):
        """Send the blank line ending the MIME headers."""
        self.wfile.seek(0)
        message_body = self.wfile.read()
        self.wfile.seek(0)
        message_body_len = len(message_body)
        self.send_header("Content-Length", str(message_body_len))
        if message_body_len > 0:
            self.send_header("Content-Type", "application/json")
        if not self.close_connection:
            self.send_header("Connection", "keep-alive")
        if self.request_version != 'HTTP/0.9':
            self._headers_buffer.append(b"\r\n")
            self.flush_headers(message_body)

    def flush_headers(self, message_body=b""):
        if hasattr(self, '_headers_buffer'):
            headers = b"".join(self._headers_buffer)
            self.wfile.write(headers)
            self.wfile.write(message_body)
            self._headers_buffer = []
