class IPFSError(Exception):
    pass


class CLIError(IPFSError):
    pass


class FeatureNotImplemented(IPFSError):
    def __init__(self, feature):
        super(FeatureNotImplemented, self).__init__(
            'Feature not implemented: %s' % feature)


class CommandNotImplemented(IPFSError):
    def __init__(self, command):
        super(CommandNotImplemented, self).__init__(
            'Command not implemented: %s' % command)

class UnknownReference(IPFSError):
    def __init__(self, ref):
        super(UnknownReference, self).__init__(
            'Unknown reference: %s' % ref)


class InvalidURL(IPFSError):
    def __init__(self, url):
        super(InvalidURL, self).__init__(
            'Invalid URL: %s' % ref)

