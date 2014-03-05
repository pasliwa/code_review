$(document).ready(function () {

    $(".confirmation-needed").click(function () {
        return confirm($(this).attr("data-question"));
    });

});

