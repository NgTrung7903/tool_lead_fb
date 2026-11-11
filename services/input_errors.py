"""Input errors with semantic locations, independent of the browser layout."""


class InputError(ValueError):
    def __init__(self, message, field, *, hint='', location=None, status_code=400):
        super().__init__(message)
        self.status_code = status_code
        self.field = field
        self.hint = hint
        self.location = list(location or ())

    def issue(self):
        return {'field': self.field, 'message': str(self), 'hint': self.hint,
                'location': self.location}
