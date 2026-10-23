"""Domain errors raised by the service layer.

Services never import FastAPI; app.main maps each error class to its HTTP status.
"""


class AppError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class AuthenticationError(AppError):
    status_code = 401


class PermissionDeniedError(AppError):
    status_code = 403


class NotFoundError(AppError):
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class BusinessValidationError(AppError):
    status_code = 422
