from colander import Invalid
from pyramid.httpexceptions import HTTPError
from pyramid.response import Response

from ichnaea.decimaljson import (
    dumps,
    loads,
)

MSG_ONE_OF = 'You need to provide a mapping with least one cell or wifi entry.'


class _JSONError(HTTPError):
    def __init__(self, errors, status=400):
        body = {'errors': errors}
        Response.__init__(self, dumps(body))
        self.status = status
        self.content_type = 'application/json'


def preprocess_request(request, schema, extra_checks=(), response=_JSONError):
    body = {}
    errors = []
    validated = {}

    if request.body:
        try:
            body = loads(request.body, encoding=request.charset)
        except ValueError as e:
            errors.append(dict(name=None, description=e.message))

    # schema validation
    schema = schema.bind(request=body)
    for attr in schema.children:
        name = attr.name
        try:
            if name not in body:
                deserialized = attr.deserialize()
            else:
                deserialized = attr.deserialize(body[name])
        except Invalid as e:
            # the struct is invalid
            err_dict = e.asdict()
            try:
                errors.append(dict(name=name, description=err_dict[name]))
            except KeyError:
                for k, v in err_dict.items():
                    if k.startswith(name):
                        errors.append(dict(name=k, description=v))
        else:
            validated[name] = deserialized

    for func in extra_checks:
        func(validated, errors)

    if errors and response is not None:
        # the response / None check is used in schema tests
        request.registry.heka_client.debug('error_handler' + repr(errors))
        raise response(errors)

    return (validated, errors)
