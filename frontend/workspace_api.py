"""Optional trustee workspace operations, isolated from the shared api.py."""
from flask import jsonify, request

def register_workspace_api(app):
    def route(path,method,endpoint):
        def decorate(handler):
            if not any(rule.rule==path and method in rule.methods for rule in app.url_map.iter_rules()):
                app.add_url_rule(path,endpoint,handler,methods=[method])
            return handler
        return decorate
    def call(method,cid,*args):
        provider=app.config.get("MANDATE_WORKSPACE_PROVIDER")
        if provider is None:return jsonify(error="The managed pot and policy-update backend is not connected."),501
        try:return jsonify(getattr(provider,method)(cid,*args))
        except KeyError:return jsonify(error="Unknown charity or stock"),404
        except PermissionError as error:return jsonify(error=str(error)),409
        except ValueError as error:return jsonify(error=str(error)),400
    @route("/api/charities/<cid>/account","GET","mandate_account")
    def account(cid):return call("account",cid)
    @route("/api/charities/<cid>/companies/<ticker>/investment-quote","GET","mandate_investment_quote")
    def quote(cid,ticker):return call("quote",cid,ticker)
    @route("/api/charities/<cid>/investments","POST","mandate_investment")
    def invest(cid):return call("buy",cid,request.get_json(silent=True) or {})
    @route("/api/charities/<cid>/policy","POST","mandate_policy_update")
    def policy(cid):return call("update_policy",cid,request.get_json(silent=True) or {})
