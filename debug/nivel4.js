$(document).ready(function () {
    $('body').find('hr').last().remove();
    if ($('#contenidoPrincipal').html() == "") {
        $('#contenidoPrincipal').remove();
    }
    if ($('#contenidoSecundario').html() == "") {
        $('#contenidoSecundario').remove();
    }
    $('.fullSH').find('.SolapaSerieClass').first().click();

    $('.fullCE').find('.SolapaSerieClass').first().click();
    $('.fullPUB').find('.SolapaSerieClass').first().click();
})

function SelectSH(e) {
    var cont = $(e).attr('data-cont');
    var supCont = $(e).parent().parent().parent();
    $(supCont).find('.contSH').each(function () {
        if ($(this).css('display') != "none" && $(this).attr('id') != cont) {
            $(this).fadeOut('normal', function () {
                $(supCont).find('#' + cont).fadeIn();
            });
        }
    })

    

    $(supCont).find('.SolapaSerieClass').each(function () {
        $(this).removeClass('a-color3-active');
    })
    $(e).addClass('a-color3-active');
}

function mostrarCenso(e) {
    var recibe = "CensoProv";
    var sale = "CensoNac";
    var ctrl = "CensoProv";
    var censo = $('#tituloCenso').text().trim().replace(" ", "-");
    if (e == "N") {
        recibe = "CensoNac";
        sale = "CensoProv";
        ctrl = "CensoNac";
    }
    if (e == "P") {
        
    }

    if (e == "S") {
        $('#CensoNac').fadeOut('normal', function () {
            $('#CensoNac').html("");
        });
        $('#CensoProv').fadeOut('normal', function () {
            $('#CensoProv').html("");
        });
        return false;
    }

    $('#' + sale).fadeOut('normal', function () {
        $('#' + recibe).fadeOut('normal', function () {
            $('#' + recibe).load("/Nivel4/" + ctrl + "/" + censo, function () {
                $('#' + recibe).fadeIn('normal');
            });
        });
    })
    
    
}


