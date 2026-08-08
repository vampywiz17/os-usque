<script>
    let enrollmentTunnel = null;
    let enrollmentPoll = null;
    let enrollmentStateRequest = 0;
    let enrollmentStatusTarget = "#enrollmentStatus";
    let enrollmentSecretTarget = "#enrollmentToken";

    function selectedTunnel(role)
    {
        const grid = $("#{{ formGridTunnel['table_id'] }}");
        const selected = grid.bootgrid("getSelectedRows");
        if (selected.length !== 1) {
            return null;
        }
        const selectedId = String(selected[0]);
        const row = grid.bootgrid("getCurrentRows").find(function(candidate) {
            return String(candidate.uuid) === selectedId;
        });
        return row !== undefined && row.role === role ? row.uuid : null;
    }

    function selectedClientTunnel()
    {
        return selectedTunnel("client");
    }

    function selectedMeshTunnel()
    {
        return selectedTunnel("mesh-node");
    }

    function updateMeshReturnRouteFields()
    {
        const isMeshNode = $("#tunnel\\.role").val() === "mesh-node";
        const meshRouteRows = $(
            "#row_tunnel\\.mesh_return_routes_enabled, " +
            "#row_tunnel\\.mesh_return_route_ipv4, " +
            "#row_tunnel\\.mesh_return_route_ipv6"
        );
        if (isMeshNode) {
            meshRouteRows.show();
        } else {
            meshRouteRows.hide();
        }
    }

    function updateEnrollmentButton()
    {
        const requestId = ++enrollmentStateRequest;
        const clientId = selectedClientTunnel();
        const meshId = selectedMeshTunnel();
        const tunnelId = clientId || meshId;
        const button = clientId !== null ? $("#registerClient") : $("#registerMesh");
        $("#registerClient, #registerMesh").prop("disabled", true).removeAttr("title");
        if (tunnelId === null) {
            return;
        }

        ajaxCall(
            "/api/usque/enrollment/registration_status/" + tunnelId,
            {},
            function(response) {
                const selectedId = selectedClientTunnel() || selectedMeshTunnel();
                if (requestId !== enrollmentStateRequest || selectedId !== tunnelId) {
                    return;
                }
                const canRegister = response.status === "ok" && response.can_register === true;
                button.prop("disabled", !canRegister);
                if (!canRegister && response.message) {
                    button.attr("title", response.message);
                }
            }
        );
    }

    function updateClientEnrollmentMethod()
    {
        const browserAssisted = $("#clientEnrollmentMethod").val() === "browser";
        $("#browserEnrollmentFields").toggle(browserAssisted);
        $("#serviceTokenEnrollmentFields").toggle(!browserAssisted);
        $("#enrollmentStatus").text("");
        if (!browserAssisted || enrollmentTunnel === null) {
            return;
        }
        $("#cloudflareLogin").attr("href", "#");
        ajaxCall("/api/usque/enrollment/login_url/" + enrollmentTunnel, {}, function(response) {
            if (response.status === "ok") {
                $("#cloudflareLogin").attr("href", response.url);
            } else {
                $("#enrollmentStatus").text(
                    response.message || "{{ lang._('Unable to create the Cloudflare login URL.') }}"
                );
            }
        });
    }

    function clearClientEnrollmentSecrets()
    {
        $("#enrollmentToken, #accessClientId, #accessClientSecret").val("");
    }

    function pollEnrollment(jobId)
    {
        ajaxCall("/api/usque/enrollment/status/" + jobId, {}, function(response) {
            $(enrollmentStatusTarget).text(response.message || response.state || "");
            if (response.state === "completed" || response.state === "failed") {
                window.clearInterval(enrollmentPoll);
                enrollmentPoll = null;
                $(enrollmentSecretTarget).val("");
                if (enrollmentStatusTarget === "#enrollmentStatus") {
                    clearClientEnrollmentSecrets();
                }
                updateEnrollmentButton();
            }
        });
    }

    $(document).ready(function() {
        mapDataToFormUI({'frm_general_settings': '/api/usque/settings/get_general'});
        const grid = $("#{{ formGridTunnel['table_id'] }}").UIBootgrid({
            search: "/api/usque/settings/search_tunnel/",
            get: "/api/usque/settings/get_tunnel/",
            set: "/api/usque/settings/set_tunnel/",
            add: "/api/usque/settings/add_tunnel/",
            del: "/api/usque/settings/del_tunnel/",
            toggle: "/api/usque/settings/toggle_tunnel/"
        });
        grid
            .on("selected.rs.jquery.bootgrid", updateEnrollmentButton)
            .on("deselected.rs.jquery.bootgrid", updateEnrollmentButton)
            .on("loaded.rs.jquery.bootgrid", updateEnrollmentButton);

        $("#{{ formGridTunnel['edit_dialog_id'] }}")
            .on("opnsense_bootgrid_mapped", updateMeshReturnRouteFields);
        $("#tunnel\\.role")
            .on("change.usqueMeshReturnRoutes", updateMeshReturnRouteFields);

        $("#registerClient").click(function() {
            enrollmentTunnel = selectedClientTunnel();
            enrollmentStatusTarget = "#enrollmentStatus";
            enrollmentSecretTarget = "#enrollmentToken, #accessClientId, #accessClientSecret";
            if (enrollmentTunnel === null) {
                return;
            }
            clearClientEnrollmentSecrets();
            $("#accessOrganization").val("");
            $("#acceptTos").prop("checked", false);
            $("#enrollmentStatus").text("");
            $("#clientEnrollmentMethod").val("browser");
            updateClientEnrollmentMethod();
            $("#enrollmentDialog").modal("show");
        });


        $("#registerMesh").click(function() {
            enrollmentTunnel = selectedMeshTunnel();
            if (enrollmentTunnel === null) {
                return;
            }
            enrollmentStatusTarget = "#meshEnrollmentStatus";
            enrollmentSecretTarget = "#meshToken";
            $("#meshToken").val("");
            $("#meshAcceptTos, #meshAcknowledgeLinux").prop("checked", false);
            $("#meshEnrollmentStatus").text("");
            $("#meshEnrollmentDialog").modal("show");
        });

        $("#clientEnrollmentMethod").on("change", updateClientEnrollmentMethod);

        $("#startEnrollment").click(function() {
            if (enrollmentTunnel === null) {
                return;
            }
            const method = $("#clientEnrollmentMethod").val();
            const accepted = $("#acceptTos").is(":checked") ? "1" : "0";
            let endpoint;
            let payload;
            if (method === "service-token") {
                endpoint = "/api/usque/enrollment/service_token_register/" + enrollmentTunnel;
                payload = {
                    organization: $("#accessOrganization").val(),
                    auth_client_id: $("#accessClientId").val(),
                    auth_client_secret: $("#accessClientSecret").val(),
                    accept_tos: accepted
                };
            } else {
                endpoint = "/api/usque/enrollment/register/" + enrollmentTunnel;
                payload = {token: $("#enrollmentToken").val(), accept_tos: accepted};
            }
            clearClientEnrollmentSecrets();
            $("#enrollmentStatus").text("{{ lang._('Starting enrollment...') }}");
            ajaxCall(endpoint, payload, function(response) {
                if (response.status !== "started") {
                    $("#enrollmentStatus").text(
                        response.message || "{{ lang._('Enrollment could not be started.') }}"
                    );
                    return;
                }
                $("#enrollmentStatus").text("{{ lang._('Enrollment worker started.') }}");
                if (enrollmentPoll !== null) {
                    window.clearInterval(enrollmentPoll);
                }
                pollEnrollment(response.job_id);
                enrollmentPoll = window.setInterval(function() {
                    pollEnrollment(response.job_id);
                }, 2000);
            });
        });


        $("#enrollmentDialog").on("hidden.bs.modal", function() {
            clearClientEnrollmentSecrets();
            $("#accessOrganization").val("");
        });

        $("#startMeshEnrollment").click(function() {
            if (enrollmentTunnel === null) {
                return;
            }
            const token = $("#meshToken").val();
            const accepted = $("#meshAcceptTos").is(":checked") ? "1" : "0";
            const acknowledged = $("#meshAcknowledgeLinux").is(":checked") ? "1" : "0";
            $("#meshToken").val("");
            $("#meshEnrollmentStatus").text("{{ lang._('Starting Mesh registration...') }}");
            ajaxCall(
                "/api/usque/enrollment/mesh_register/" + enrollmentTunnel,
                {
                    token: token,
                    accept_tos: accepted,
                    acknowledge_linux_platform_claim: acknowledged
                },
                function(response) {
                    if (response.status !== "started") {
                        $("#meshEnrollmentStatus").text(
                            response.message || "{{ lang._('Mesh registration could not be started.') }}"
                        );
                        return;
                    }
                    $("#meshEnrollmentStatus").text("{{ lang._('Mesh registration worker started.') }}");
                    if (enrollmentPoll !== null) {
                        window.clearInterval(enrollmentPoll);
                    }
                    pollEnrollment(response.job_id);
                    enrollmentPoll = window.setInterval(function() {
                        pollEnrollment(response.job_id);
                    }, 2000);
                }
            );
        });

        $("#meshEnrollmentDialog").on("hidden.bs.modal", function() {
            $("#meshToken").val("");
        });

        $("#applyService").click(function() {
            const button = $(this);
            saveFormToEndpoint("/api/usque/settings/set_general", "frm_general_settings", function() {
                button.prop("disabled", true);
                $("#applyServiceProgress").addClass("fa fa-spinner fa-pulse");
                ajaxCall("/api/usque/service/reconfigure", {}, function(response, status) {
                    button.prop("disabled", false);
                    $("#applyServiceProgress").removeClass("fa fa-spinner fa-pulse");
                    if (status !== "success" || response.status !== "ok") {
                        BootstrapDialog.show({
                            type: BootstrapDialog.TYPE_DANGER,
                            title: "{{ lang._('usque service') }}",
                            message: response.message || response.response || "{{ lang._('Unable to apply the tunnel configuration.') }}"
                        });
                    }
                });
            });
        });
    });
</script>

<div class="content-box">
    {{ partial('layout_partials/base_form', ['fields': formGeneral, 'id': 'frm_general_settings']) }}
    <div class="col-md-12">
        <h2>{{ lang._('usque tunnels') }}</h2>
        <p>
            {{ lang._('Egress clients and ingress Mesh nodes are separate tunnel instances. OPNsense owns routing and firewall policy; usque remains tunnel-only.') }}
        </p>
        <button id="registerClient" class="btn btn-primary" type="button" disabled>
            <i class="fa fa-cloud-upload"></i>
            {{ lang._('Register selected egress client') }}
        </button>
        <button id="registerMesh" class="btn btn-primary" type="button" disabled>
            <i class="fa fa-cloud-upload"></i>
            {{ lang._('Register selected Mesh node') }}
        </button>
        <button id="applyService" class="btn btn-primary" type="button">
            <i class="fa fa-check"></i>
            {{ lang._('Apply changes') }}
            <i id="applyServiceProgress"></i>
        </button>
    </div>
    <div class="col-md-12">
        {{ partial('layout_partials/base_bootgrid_table', formGridTunnel) }}
    </div>
</div>

{{ partial("layout_partials/base_dialog", [
    'fields': formDialogTunnel,
    'id': formGridTunnel['edit_dialog_id'],
    'label': lang._('Edit tunnel')
]) }}

<div class="modal fade" id="enrollmentDialog" tabindex="-1" role="dialog" aria-labelledby="enrollmentTitle">
    <div class="modal-dialog" role="document">
        <div class="modal-content">
            <div class="modal-header">
                <button type="button" class="close" data-dismiss="modal" aria-label="{{ lang._('Close') }}">
                    <span aria-hidden="true">&times;</span>
                </button>
                <h4 class="modal-title" id="enrollmentTitle">{{ lang._('Cloudflare egress client registration') }}</h4>
            </div>
            <div class="modal-body">
                <div class="form-group">
                    <label for="clientEnrollmentMethod">{{ lang._('Registration method') }}</label>
                    <select id="clientEnrollmentMethod" class="form-control">
                        <option value="browser">{{ lang._('Browser-assisted identity enrollment') }}</option>
                        <option value="service-token">{{ lang._('Cloudflare Access service token') }}</option>
                    </select>
                </div>
                <div id="browserEnrollmentFields">
                    <ol>
                        <li>
                            <a id="cloudflareLogin" href="#" target="_blank" rel="noopener noreferrer">
                                {{ lang._('Open the configured Cloudflare team login') }}
                            </a>
                        </li>
                        <li>{{ lang._('Authenticate with the organization identity provider.') }}</li>
                        <li>{{ lang._('Copy the resulting com.cloudflare.warp callback URI and paste it below. The private device key is generated on OPNsense and never enters the browser.') }}</li>
                    </ol>
                    <div class="form-group">
                        <label for="enrollmentToken">{{ lang._('One-time callback URI or enrollment JWT') }}</label>
                        <textarea id="enrollmentToken" class="form-control" rows="4" autocomplete="off" spellcheck="false"></textarea>
                    </div>
                </div>
                <div id="serviceTokenEnrollmentFields" style="display: none;">
                    <div class="alert alert-info">
                        {{ lang._('The service token must be included by a Service Auth policy attached to Cloudflare Device Enrollment permissions. An Allow policy is not sufficient.') }}
                    </div>
                    <div class="form-group">
                        <label for="accessOrganization">{{ lang._('Cloudflare Zero Trust organization') }}</label>
                        <input id="accessOrganization" class="form-control" type="text" maxlength="63" autocomplete="off" spellcheck="false">
                    </div>
                    <div class="form-group">
                        <label for="accessClientId">{{ lang._('Access Client ID') }}</label>
                        <input id="accessClientId" class="form-control" type="text" maxlength="512" autocomplete="off" spellcheck="false">
                    </div>
                    <div class="form-group">
                        <label for="accessClientSecret">{{ lang._('Access Client Secret (key)') }}</label>
                        <input id="accessClientSecret" class="form-control" type="password" maxlength="4096" autocomplete="new-password" spellcheck="false">
                    </div>
                    <p class="help-block">
                        {{ lang._('The Client ID and secret are used once, are not saved in config.xml, and are removed from temporary storage when registration finishes.') }}
                    </p>
                </div>
                <div class="checkbox">
                    <label>
                        <input id="acceptTos" type="checkbox">
                        {{ lang._('I accept the Cloudflare Application Terms for this registration.') }}
                    </label>
                </div>
                <p id="enrollmentStatus" class="help-block" aria-live="polite"></p>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-default" data-dismiss="modal">{{ lang._('Close') }}</button>
                <button type="button" class="btn btn-primary" id="startEnrollment">{{ lang._('Register') }}</button>
            </div>
        </div>
    </div>
</div>
<div class="modal fade" id="meshEnrollmentDialog" tabindex="-1" role="dialog" aria-labelledby="meshEnrollmentTitle">
    <div class="modal-dialog" role="document">
        <div class="modal-content">
            <div class="modal-header">
                <button type="button" class="close" data-dismiss="modal" aria-label="{{ lang._('Close') }}">
                    <span aria-hidden="true">&times;</span>
                </button>
                <h4 class="modal-title" id="meshEnrollmentTitle">{{ lang._('Cloudflare Mesh node registration') }}</h4>
            </div>
            <div class="modal-body">
                <div class="alert alert-warning">
                    {{ lang._('Cloudflare currently documents Mesh nodes for its Linux client. This independent FreeBSD implementation must make an acknowledged Linux compatibility claim during registration. It is not an official client; Cloudflare may detect, reject, restrict, or sanction its use. Use is entirely at your own risk, and the authors accept no liability for resulting account or service action.') }}
                </div>
                <p>
                    {{ lang._('Paste the connector token generated for this Mesh node. The token is passed once through a root-only temporary file and is not saved in config.xml or application logs.') }}
                </p>
                <div class="form-group">
                    <label for="meshToken">{{ lang._('Mesh connector token') }}</label>
                    <textarea id="meshToken" class="form-control" rows="4" autocomplete="off" spellcheck="false"></textarea>
                </div>
                <div class="checkbox">
                    <label>
                        <input id="meshAcceptTos" type="checkbox">
                        {{ lang._('I accept the Cloudflare Application Terms for this registration.') }}
                    </label>
                </div>
                <div class="checkbox">
                    <label>
                        <input id="meshAcknowledgeLinux" type="checkbox">
                        {{ lang._('I understand and accept the Linux platform compatibility claim and its risks.') }}
                    </label>
                </div>
                <p id="meshEnrollmentStatus" class="help-block" aria-live="polite"></p>
            </div>
            <div class="modal-footer">
                <button type="button" class="btn btn-default" data-dismiss="modal">{{ lang._('Close') }}</button>
                <button type="button" class="btn btn-primary" id="startMeshEnrollment">{{ lang._('Register Mesh node') }}</button>
            </div>
        </div>
    </div>
</div>
