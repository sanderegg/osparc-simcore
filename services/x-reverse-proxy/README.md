# x reverse proxy service

A standalong traffik-based service used to redirect the traffic of backend interactive services, which are routed on ``/x/{node_uuid}``, to the user. This was previously handled by the webserver but delegated to this traffik-based standalone service

All traffic going that needs to be reverse-proxied by the internal traefik instance must be labelled with io.simcore.zone: ${TRAEFIK_SIMCORE_ZONE} or it will be picked up by the external Traefik instance.

## Development

the traefik dashboard when running the stack in devel mode (traefik does not handle 2 dashboards at the moment)
- in devel mode, the traefik UI is accessible through http://127.0.0.1:8080
