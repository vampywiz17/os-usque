<script>
    let enrollmentTunnel = null;
    let enrollmentPoll = null;

    function selectedTunnel()
    {
        const rows = $("#{{ formGridTunnel['table_id'] }}").bootgrid("getSelectedRows");
        return rows.length === 1 ? rows[0] : null;
    }

    function updateEnrollmentButton()
    {
        $("#registerClient").prop("disabled", selectedTunnel() === null);
    }

    function pollEnrollment(jobId)
    {
        ajaxCall("/api/usque/enrollment/status/" + jobId, {}, function(response) {
            $("#enrollmentStatus").text(response.message || response.state || "");
            if (response.state === "completed" || response.state === "failed") {
                window.clearInterval(enrollmentPoll);
                enrollmentPoll = null;
                $("#enrollmentToken").val("");
            }
        });
    }

    $(document).ready(function() {
        const grid = $("#{{ formGridTunnel['table_id'] }}");
        grid.UIBootgrid({
            search: "/api/usque/settings/search_tunnel/",
            get: "/api/usque/settings/get_tunnel/",
            set: "/api/usque/settings/set_tunnel/",
            add: "/api/usque/settings/add_tunnel/",
            del: "/api/usque/settings/del_tunnel/",
            toggle: "/api/usque/settings/toggle_tunnel/"
        });
        grid.on("selected.rs.jquery.bootgrid deselected.rs.jquery.bootgrid", updateEnrollmentButton);

        $("#registerClient").click(function() {
            enrollmentTunnel = selectedTunnel();
            if (enrollmentTunnel === null) {
                return;
            }
            ajaxCall("/api/usque/enrollment/login_url/" + enrollmentTunnel, {}, function(response) {
                if (response.status !== "ok") {
                    BootstrapDialog.show({
                        type: BootstrapDialog.TYPE_DANGER,
                        title: "{{ lang._('Enrollment') }}",
                        message: response.message || "{{ lang._('Unable to create the Cloudflare login URL.') }}"
                    });
                    return;
                }
                $("#cloudflareLogin").attr("href", response.url);
                $("#enrollmentToken").val("");
                $("#acceptTos").prop("checked", false);
                $("#enrollmentStatus").text("");
                $("#enrollmentDialog").modal("show");
            });
        });

        $("#startEnrollment").click(function() {
            if (enrollmentTunnel === null) {
                return;
            }
            const token = $("#enrollmentToken").val();
            const accepted = $("#acceptTos").is(":checked") ? "1" : "0";
            $("#enrollmentToken").val("");
            $("#enrollmentStatus").text("{{ lang._('Starting enrollment...') }}");
            ajaxCall(
                "/api/usque/enrollment/register/" + enrollmentTunnel,
                {token: token, accept_tos: accepted},
                function(response) {
                    if (response.status !== "started") {
                        $("#enrollmentStatus").text(response.message || "{{ lang._('Enrollment could not be started.') }}");
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
                }
            );
        });

        $("#enrollmentDialog").on("hidden.bs.modal", function() {
            $("#enrollmentToken").val("");
        });
    });
</script>

<div class="content-box">
    <div class="col-md-12">
        <h2>{{ lang._('usque tunnels') }}</h2>
        <p>
            {{ lang._('Egress clients and ingress Mesh nodes are separate tunnel instances. OPNsense owns routing and firewall policy; usque remains tunnel-only.') }}
        </p>
        <button id="registerClient" class="btn btn-primary" type="button" disabled>
            <i class="fa fa-cloud-upload"></i>
            {{ lang._('Register selected egress client') }}
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
                <h4 class="modal-title" id="enrollmentTitle">{{ lang._('Browser-assisted Cloudflare enrollment') }}</h4>
            </div>
            <div class="modal-body">
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
