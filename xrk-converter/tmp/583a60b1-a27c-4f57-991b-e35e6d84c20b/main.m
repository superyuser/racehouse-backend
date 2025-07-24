function main()
    try
        AutoExportXrkData();
    catch ME
        disp(getReport(ME));
        exit(1);
    end
    exit(0);

    
end
