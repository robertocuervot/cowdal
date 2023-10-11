readChannelID = 2294535;

fieldID1 = 1;
fieldID2 = 2;
fieldID3 = 3;

readAPIKey = 'OFGC8F33ESQ2OR9D';

%% Lectura de los datos %%

[data1, time1] = thingSpeakRead(readChannelID, 'Field', fieldID1, 'NumPoints', 100, 'ReadKey', readAPIKey);
[data2, time2] = thingSpeakRead(readChannelID, 'Field', fieldID2, 'NumPoints', 100, 'ReadKey', readAPIKey);
[data3, time3] = thingSpeakRead(readChannelID, 'Field', fieldID3, 'NumPoints', 100, 'ReadKey', readAPIKey);
plotsize=10
buff=zeros(plotsize,1); %genero un vector de 50 instancias que sera utilizado mas adelante
iter=plotsize; %variable utilizada para llenar el vector de datos
timeplot=time3(1:plotsize); %genero un vector de objetos day/time para plotear la informacion con su tiempo respectivo
tam=size(data3); %tamano del ciclo for
for i=tam:-1:1 %recorro todos los 5000 items leidos de cada field desde los mas nuevos
    if data2(i)==0 %si el valor leido es del sensor tipo 0 (temperatura) entro a leer el valor
        if iter>0 % solo voy a plotear 50 iteraciones
            buff(iter)=data3(i);
            timeplot(iter)=time3(i);
            iter=iter-1;
        end
    end
end
buff
timeplot
%% creacion del grafico %%
figure
plot(timeplot,buff,'Color',[0,0.7,0.9])
title('Sensor de Temperatura')
xlabel('tiempo')
ylabel('Temperatura')
%plot(timeplot, buff);​